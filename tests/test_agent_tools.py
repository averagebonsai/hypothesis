"""Host tests operate on bundle bytes and mocked Docker transport, never extensions."""

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_tools.bundles import copy_trusted_context, seal_bundle, snapshot_bundle, verify_bundle
from agent_tools.docker_worker import DockerWorker
from agent_tools.inventory import compatibility_findings, inventory
from agent_tools.process import ProcessLimitError, ProcessResult, bounded_command
from agent_tools.specs import (
    VALIDATION_CHECKS,
    BundleManifest,
    CheckResult,
    GapAnalysisReport,
    WorkerResponse,
)
from simulation_core.execution import JobManifest

PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture
def bundle(tmp_path):
    # Synthetic data fixtures: the trusted image never embeds experimental source.
    root = tmp_path / "experimental_components/vector_allocation/v1"
    (root / "experiment_extension").mkdir(parents=True)
    (root / "tests").mkdir()
    data = {
        "experiment_id": "vector_allocation",
        "version": "v1",
        "gap_analysis": {
            "objective": "Synthetic planning fixture",
            "decisions": [
                {
                    "requirement": {
                        "id": "execution",
                        "description": "Generic execution",
                        "action_shape": "vector",
                    },
                    "disposition": "REUSE",
                    "selected_components": ["scripted.v1"],
                    "reason": "Generic policy",
                },
                {
                    "requirement": {
                        "id": "payload",
                        "description": "Vector payload",
                        "action_shape": "vector",
                    },
                    "disposition": "EXTEND",
                    "reason": "New payload schema",
                },
            ],
        },
        "components": [
            {
                "id": "experimental.vector_allocation.action.v1",
                "kind": "action_schema",
                "purpose": "Synthetic data-only fixture",
                "gap_id": "payload",
                "parent_interface": "pydantic.BaseModel",
                "symbol": "experiment_extension.synthetic:Payload",
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "acceptance_tests": [
                    {
                        "name": "test_fixture",
                        "category": "interface",
                        "expected": "Typed payload",
                        "reference": "Synthetic test contract",
                    }
                ],
            }
        ],
    }
    (root / "bundle.json").write_text(json.dumps(data))
    (root / "experiment_extension/__init__.py").write_text("")
    (root / "experiment_extension/synthetic.py").write_text(
        'raise RuntimeError("Must never import on host")\n'
    )
    (root / "tests/test_allocation.py").write_text("def test_fixture(): pass\n")
    (root / "README.md").write_text("Synthetic test bundle")
    from examples.measurements import run_job

    (root / "job.example.json").write_text(run_job().manifest.model_dump_json())
    return root


def test_bundle_inspection_never_imports_experimental_python(bundle):
    (bundle / "experiment_extension/__init__.py").write_text(
        'raise AssertionError("Host imported untrusted code")\n'
    )
    seal = seal_bundle(bundle)
    manifest, found, _ = verify_bundle(bundle)
    assert manifest.experiment_id == "vector_allocation" and found == seal
    assert not any(name.startswith("experiment_extension") for name in sys.modules)


def test_sealed_source_or_acceptance_change_requires_a_new_version(bundle):
    seal_bundle(bundle)
    (bundle / "tests/test_allocation.py").write_text("def test_weakened(): pass\n")
    with pytest.raises(ValueError, match="changed"):
        verify_bundle(bundle)
    with pytest.raises(ValueError, match="new version"):
        seal_bundle(bundle)


@pytest.mark.parametrize("kind", ["file_symlink", "dir_symlink", "hardlink", "unexpected"])
def test_unsafe_bundle_files_are_rejected(bundle, tmp_path, kind):
    secret = tmp_path / "secret.txt"
    secret.write_text("must not be copied")
    if kind == "file_symlink":
        (bundle / "experiment_extension/leak.py").symlink_to(secret)
    elif kind == "dir_symlink":
        (bundle / "experiment_extension/leak").symlink_to(tmp_path, target_is_directory=True)
    elif kind == "hardlink":
        (bundle / "experiment_extension/leak.py").hardlink_to(secret)
    else:
        (bundle / ".env").write_text("API_KEY=must-not-copy")
    with pytest.raises((ValueError, OSError)):
        seal_bundle(bundle)


def test_snapshot_binds_validation_to_exact_bytes_and_excludes_reports(bundle, tmp_path):
    seal = seal_bundle(bundle)
    snapshot = tmp_path / "snapshot"
    assert snapshot_bundle(bundle, snapshot) == seal
    _, found, _ = verify_bundle(snapshot, check_location=False)
    assert found == seal
    (bundle / "README.md").write_text("Changed after snapshot")
    assert verify_bundle(snapshot, check_location=False)[1] == seal


def test_critical_unknowns_block_sealing(bundle):
    data = json.loads((bundle / "bundle.json").read_text())
    data["gap_analysis"]["decisions"][0]["unresolved"] = ["Unknown budget"]
    (bundle / "bundle.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match="critical unknowns"):
        seal_bundle(bundle)


def test_bad_reuse_detects_scalar_vector_mismatch(bundle):
    data = json.loads((bundle / "bundle.json").read_text())["gap_analysis"]
    data["decisions"][0]["selected_components"] = ["numerical_nash.v1"]
    report = GapAnalysisReport.from_json_values(data)
    assert "not vector" in compatibility_findings(report)[0]
    assert "shared_tools" in inventory()


def test_specs_require_approved_parents_and_allow_uncapped_repair_counts(bundle):
    data = json.loads((bundle / "bundle.json").read_text())
    data["components"][0]["parent_interface"] = "arbitrary.Import"
    with pytest.raises(ValidationError):
        BundleManifest.from_json_values(data)
    data = json.loads((bundle / "bundle.json").read_text())
    data["repair_counts"] = {"failure-1": 3}
    assert BundleManifest.from_json_values(data).repair_counts["failure-1"] == 3
    data["repair_counts"] = {"failure-1": -1}
    with pytest.raises(ValidationError, match="nonnegative"):
        BundleManifest.from_json_values(data)
    data["repair_counts"] = {}
    data["existing_dependencies"] = ["simultaneous.v1"]
    with pytest.raises(ValidationError):
        BundleManifest.from_json_values(data)


def test_build_context_is_explicit_and_has_no_secrets_or_extensions(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    for name in ("src", "tests", "docker", "experimental_components"):
        (project / name).mkdir()
    for name in ("pyproject.toml", "uv.lock", ".env"):
        (project / name).write_text(name)
    (project / "experimental_components/evil.py").write_text("raise Exception()")
    (project / "prompts").mkdir()
    (project / "prompts/blind_coding_agent.md").write_text("Safe authoring instructions")
    (project / "prompts/private_old_results.md").write_text("Do not copy")
    context = tmp_path / "context"
    assert len(copy_trusted_context(project, context)) == 64
    assert not (context / ".env").exists()
    assert not (context / "experimental_components").exists()
    assert (context / "prompts/blind_coding_agent.md").read_text() == "Safe authoring instructions"
    assert not (context / "prompts/private_old_results.md").exists()


def test_restricted_container_flags_and_sbx_transport():
    worker = DockerWorker(PROJECT, sandbox="hypothesis-worker")
    args = worker.run_arguments(
        "trial", "/tmp/stage/bundle", "/tmp/stage/job", "sha256:" + "a" * 64, "run", "b" * 64
    )
    assert args[:5] == ["sbx", "exec", "hypothesis-worker", "docker", "run"]
    for required in (
        "--read-only",
        "--network",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--pids-limit",
        "--memory",
        "--memory-swap",
        "--cpus",
    ):
        assert required in args
    assert not any("docker.sock" in arg or ".env" in arg for arg in args)
    assert args.count("--mount") == 2
    assert "--privileged" not in args


def test_mount_delimiters_and_bad_sandbox_names_rejected():
    with pytest.raises(ValueError):
        DockerWorker(PROJECT, sandbox="--bad-name")
    with pytest.raises(ValueError, match="delimiter"):
        DockerWorker(PROJECT).run_arguments(
            "trial", "/tmp/path,readonly=false", "/tmp/job", "image", "run", "hash"
        )


def test_worker_response_and_result_are_retained_without_experimental_imports(bundle, monkeypatch):
    seal = seal_bundle(bundle)
    job = JobManifest.model_validate_json((bundle / "job.example.json").read_text())
    commands = []

    def command(args, **kwargs):
        commands.append(args)
        if "inspect" in args:
            return ProcessResult(0, "sha256:" + "a" * 64 + "\n", "")
        response = WorkerResponse(
            bundle_digest=seal.digest,
            checks=tuple(
                CheckResult(name=name, passed=True, exit_code=0, output="Mocked transport only")
                for name in sorted(VALIDATION_CHECKS)
            ),
        )
        return ProcessResult(0, response.model_dump_json(), "")

    monkeypatch.setattr("agent_tools.docker_worker.bounded_command", command)
    monkeypatch.setattr("agent_tools.docker_worker.subprocess.run", lambda *a, **kw: None)
    receipt = DockerWorker(PROJECT).execute(bundle, job, operation="validate")
    assert receipt.response.passed
    assert receipt.limits == DockerWorker(PROJECT).limits
    assert any("run" in args for args in commands)
    receipts = list((bundle.parent.parent / "_runs/vector_allocation/v1").glob("*.json"))
    assert receipts and receipts[0].stat().st_mode & 0o777 == 0o600
    assert verify_bundle(bundle)[1] == seal


def test_timeout_always_attempts_container_cleanup(bundle, monkeypatch):
    seal_bundle(bundle)
    job = JobManifest.model_validate_json((bundle / "job.example.json").read_text())
    cleanup = []

    def command(args, **kwargs):
        if "inspect" in args:
            return ProcessResult(0, "sha256:" + "a" * 64, "")
        raise ProcessLimitError("timeout")

    monkeypatch.setattr("agent_tools.docker_worker.bounded_command", command)
    monkeypatch.setattr(
        "agent_tools.docker_worker.subprocess.run", lambda args, **kw: cleanup.append(args)
    )
    with pytest.raises(ProcessLimitError):
        DockerWorker(PROJECT).execute(bundle, job)
    assert any("--force" in args for args in cleanup)


def test_bounded_transport_limits_output_and_time():
    with pytest.raises(ProcessLimitError, match="output"):
        bounded_command([sys.executable, "-c", "print('x'*100000)"], seconds=5, max_bytes=1000)
    with pytest.raises(ProcessLimitError, match="wall-clock"):
        bounded_command(
            [sys.executable, "-c", "import time; time.sleep(10)"], seconds=1, max_bytes=1000
        )
    result = bounded_command([sys.executable, "-c", "print('ok')"], seconds=5, max_bytes=1000)
    assert result.code == 0 and result.stdout.strip() == "ok"


def test_worker_cannot_import_extensions_on_host(monkeypatch):
    from extension_worker.runtime import load_registry

    monkeypatch.setattr(
        "extension_worker.runtime.require_container",
        lambda: (_ for _ in ()).throw(RuntimeError("container required")),
    )
    with pytest.raises(RuntimeError, match="container required"):
        load_registry(Path("/untrusted/bundle"))


def test_partial_or_duplicate_validation_cannot_report_success():
    partial = WorkerResponse(
        bundle_digest="x", checks=(CheckResult(name="ruff", passed=True, exit_code=0, output="ok"),)
    )
    assert not partial.passed
    with pytest.raises(ValidationError, match="distinct"):
        WorkerResponse(bundle_digest="x", checks=partial.checks + partial.checks)


def test_trusted_build_context_rejects_links_to_external_files(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    for name in ("src", "tests", "docker"):
        (project / name).mkdir()
    for name in ("pyproject.toml", "uv.lock"):
        (project / name).write_text("trusted fixture")
    secret = tmp_path / "outside-secret"
    secret.write_text("must not copy")
    (project / "src/alias.py").symlink_to(secret)
    with pytest.raises(ValueError, match="symbolic links"):
        copy_trusted_context(project, tmp_path / "context")


def test_worker_persists_checkpoint_on_timeout_and_requires_explicit_matching_resume(
    bundle,
    monkeypatch,
    tmp_path,
):
    from components.library import standard_registry
    from simulation_core.checkpoint import RuntimeOptions
    from simulation_core.runtime import SimulationRuntime

    seal = seal_bundle(bundle)
    job = JobManifest.model_validate_json((bundle / "job.example.json").read_text())
    snapshots = []
    SimulationRuntime(standard_registry(), RuntimeOptions(on_checkpoint=snapshots.append)).run(
        job.simulation
    )
    snapshot = snapshots[-1]
    recovery = tmp_path / "current-run"
    interrupted = True
    runs = []

    def command(args, **kwargs):
        nonlocal interrupted
        if "inspect" in args:
            return ProcessResult(0, "sha256:" + "a" * 64, "")
        job_mount = next(a for a in args if a.startswith("type=bind,") and "dst=/job," in a)
        job_dir = Path(job_mount.split("src=", 1)[1].split(",dst=", 1)[0])
        runs.append((job_dir / "checkpoint.json").exists())
        if interrupted:
            interrupted = False
            kwargs["on_stderr_line"](
                "HYPOTHESIS_CHECKPOINT:"
                + json.dumps(
                    {
                        **snapshot.model_dump(mode="json"),
                        "event_count": len(snapshot.events),
                    }
                )
            )
            raise ProcessLimitError("offline simulated timeout")
        assert json.loads((job_dir / "checkpoint.json").read_text()) == snapshot.model_dump(
            mode="json"
        )
        response = WorkerResponse(
            bundle_digest=seal.digest,
            checks=tuple(
                CheckResult(name=name, passed=True, exit_code=0, output="Mocked transport")
                for name in sorted(VALIDATION_CHECKS)
            ),
        )
        return ProcessResult(0, response.model_dump_json(), "")

    monkeypatch.setattr("agent_tools.docker_worker.bounded_command", command)
    monkeypatch.setattr("agent_tools.docker_worker.subprocess.run", lambda *args, **kwargs: None)
    worker = DockerWorker(PROJECT)
    with pytest.raises(ProcessLimitError):
        worker.execute(bundle, job, checkpoint_dir=recovery)
    assert (recovery / "checkpoint.json").stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="explicit resume"):
        worker.execute(bundle, job, checkpoint_dir=recovery)
    changed = job.model_copy(
        update={"simulation": job.simulation.model_copy(update={"max_steps": 1})}
    )
    with pytest.raises(ValueError, match="Resume identity"):
        worker.execute(bundle, changed, checkpoint_dir=recovery, resume=True)
    receipt = worker.execute(bundle, job, checkpoint_dir=recovery, resume=True)
    assert receipt.checkpoint_directory == str(recovery)
    assert receipt.elapsed_seconds > 0
    assert runs == [False, True]
