"""Docker transport with an optional sbx outer VM; experimental code is data here."""

import fcntl
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from typing import Literal
from uuid import uuid4

from pydantic import JsonValue

from simulation_core.execution import JobManifest, JobResult
from simulation_core.model_gateway import ModelGateway

from .bundles import copy_trusted_context, snapshot_bundle, verify_bundle
from .execution_settings import ActorExecutionSettings
from .jobs import ToolJobManifest
from .notebooks import export_diagnostic, export_notebook, validate_notebook_json
from .process import bounded_command
from .specs import ReportReceipt, ReportResponse, RunReceipt, WorkerLimits, WorkerResponse


class DockerWorker:
    def __init__(
        self,
        project: Path,
        *,
        sandbox: str | None = None,
        docker: str = "docker",
        sbx: str = "sbx",
        limits: WorkerLimits | None = None,
        actor_gateway: ModelGateway | None = None,
        actor_model: str | None = None,
        actor_settings: ActorExecutionSettings | None = None,
    ) -> None:
        self.project = project.resolve()
        self.sandbox = sandbox
        self.docker = docker
        self.sbx = sbx
        self.limits = limits or WorkerLimits()
        if (actor_gateway is None) != (actor_model is None):
            raise ValueError("Actor gateway and allowed model must be configured together")
        self.actor_gateway = actor_gateway
        self.actor_model = actor_model
        self.actor_settings = actor_settings or (
            ActorExecutionSettings(model=actor_model) if actor_model is not None else None
        )
        if self.actor_settings is not None and self.actor_settings.model != actor_model:
            raise ValueError("Actor settings and relay model must agree")
        if sandbox and not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.-]+", sandbox):
            raise ValueError("Invalid sandbox name")

    def _docker(self, *args: str) -> list[str]:
        prefix = [self.sbx, "exec", self.sandbox, self.docker] if self.sandbox else [self.docker]
        return [*prefix, *args]

    @staticmethod
    def report_progress(line: str) -> None:
        prefix = "HYPOTHESIS_WORKER_PROGRESS:"
        if line.startswith(prefix):
            try:
                event = json.loads(line[len(prefix) :])
                if event.get("stage") in {
                    "ruff",
                    "mypy",
                    "acceptance",
                    "regressions",
                    "simulation",
                    "report",
                }:
                    print(f"[worker] {event['stage']}: {event.get('status', '')}", flush=True)
            except (ValueError, AttributeError):
                pass

    def create_sandbox(self) -> None:
        if not self.sandbox:
            raise ValueError("Choose a sandbox name")
        # No workspace, shared skills, credentials, or host Docker socket.
        result = bounded_command(
            [
                self.sbx,
                "create",
                "--name",
                self.sandbox,
                "--cpus",
                str(self.limits.cpus),
                "--memory",
                f"{self.limits.memory_mb}m",
                "--skills",
                "off",
                "shell",
            ],
            seconds=300,
            max_bytes=100_000,
        )
        if result.code:
            raise RuntimeError(f"Sandbox creation failed: {result.stderr[-4000:]}")

    def _copy_to_sandbox(self, source: Path, destination: str) -> None:
        result = bounded_command(
            [self.sbx, "cp", str(source), f"{self.sandbox}:{destination}"],
            seconds=60,
            max_bytes=100_000,
        )
        if result.code:
            raise RuntimeError(f"Sandbox copy failed: {result.stderr[-2000:]}")

    def prepare(self) -> dict[str, str]:
        """Build only trusted framework/locked dependencies, without extension files."""
        with TemporaryDirectory(prefix="hypothesis-build-") as temporary:
            context = Path(temporary) / "context"
            digest = copy_trusted_context(self.project, context)
            tag = f"hypothesis-worker:{digest[:20]}"
            try:
                cached = self.image_id(tag)
            except RuntimeError:
                pass
            else:
                return {"image_id": cached, "framework_digest": digest}
            if self.sandbox:
                space = bounded_command(
                    [self.sbx, "exec", self.sandbox, "df", "-Pk", "/var/lib/docker"],
                    seconds=30,
                    max_bytes=10000,
                )
                if space.code:
                    raise RuntimeError("Cannot check worker disk space before image build")
                available_kb = int(space.stdout.strip().splitlines()[-1].split()[3])
                if available_kb < 1_500_000:
                    raise RuntimeError(
                        "Docker worker needs at least 1.5 GB free before building; reclaim unused image/build cache, preserving experiment files"
                    )
            build_path = str(context)
            remote = f"/tmp/hypothesis-build-{uuid4().hex}"
            try:
                if self.sandbox:
                    self._copy_to_sandbox(context, remote)
                    build_path = remote
                result = bounded_command(
                    self._docker(
                        "build",
                        "--file",
                        f"{build_path}/docker/worker.Dockerfile",
                        "--tag",
                        tag,
                        build_path,
                    ),
                    seconds=900,
                    max_bytes=2_000_000,
                )
                if result.code:
                    raise RuntimeError(
                        f"Trusted worker image build failed: {result.stderr[-8000:]} {result.stdout[-2000:]}"
                    )
                return {"image_id": self.image_id(tag), "framework_digest": digest}
            finally:
                if self.sandbox:
                    # Only our uniquely named temporary directory in the outer VM.
                    subprocess.run(
                        [self.sbx, "exec", self.sandbox, "rm", "-rf", remote],
                        capture_output=True,
                        timeout=20,
                        check=False,
                    )

    def image_id(self, reference: str) -> str:
        result = bounded_command(
            self._docker("image", "inspect", "--format", "{{.Id}}", reference),
            seconds=30,
            max_bytes=4096,
        )
        value = result.stdout.strip()
        if result.code or not re.fullmatch(r"sha256:[a-f0-9]{64}", value):
            raise RuntimeError(
                "Worker image missing or invalid; prepare the trusted worker image first"
            )
        return value

    def run_arguments(
        self,
        name: str,
        bundle_path: str,
        job_path: str,
        image: str,
        operation: str,
        bundle_digest: str,
    ) -> list[str]:
        for path in (bundle_path, job_path):
            if any(char in path for char in (",", "\n", "\r")):
                raise ValueError("Mount path contains unsupported delimiter")
        return self._docker(
            "run",
            *(
                ["--interactive", "--env", "HYPOTHESIS_ENABLE_ACTORS=1"]
                if self.actor_gateway and operation in {"run", "validate"}
                else []
            ),
            "--rm",
            "--name",
            name,
            "--pull",
            "never",
            "--init",
            "--user",
            "10001:10001",
            "--read-only",
            "--network",
            "none",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--pids-limit",
            str(self.limits.pids),
            "--cpus",
            str(self.limits.cpus),
            "--memory",
            f"{self.limits.memory_mb}m",
            "--memory-swap",
            f"{self.limits.memory_mb}m",
            "--ulimit",
            "nofile=128:128",
            "--ipc",
            "private",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=268435456,mode=1777",
            "--mount",
            f"type=bind,src={bundle_path},dst=/bundle,readonly",
            "--mount",
            f"type=bind,src={job_path},dst=/job,readonly",
            *(["--entrypoint", "python"] if operation in {"preview", "report"} else []),
            image,
            *(["-m", "extension_worker.reporting"] if operation in {"preview", "report"} else []),
            operation,
            bundle_digest,
        )

    def execute(
        self,
        bundle: Path,
        job: JobManifest | ToolJobManifest,
        *,
        operation: Literal["validate", "run"] = "run",
        probes: tuple[JobManifest, ...] = (),
        checkpoint_dir: Path | None = None,
        resume: bool = False,
    ) -> RunReceipt:
        manifest, original_seal, _ = verify_bundle(bundle)
        if isinstance(job, ToolJobManifest) and probes:
            raise ValueError("Simulation probes do not apply to direct tools")
        # An image tag is derived from current trusted inputs and resolved to an immutable image ID.
        with TemporaryDirectory(prefix="hypothesis-run-") as temporary:
            root = Path(temporary)
            context = root / "context"
            framework_digest = copy_trusted_context(self.project, context)
            image = self.image_id(f"hypothesis-worker:{framework_digest[:20]}")
            stage = root / "stage"
            stage.mkdir(mode=0o755)
            seal = snapshot_bundle(bundle, stage / "bundle")
            if seal != original_seal:
                raise ValueError("Bundle changed before staging")
            job_dir = stage / "job"
            job_dir.mkdir(mode=0o755)
            manifest_path = job_dir / "manifest.json"
            manifest_path.write_text(job.model_dump_json())
            manifest_path.chmod(0o644)
            if probes:
                (job_dir / "probes.json").write_text(
                    json.dumps([probe.model_dump(mode="json") for probe in probes])
                )
                (job_dir / "probes.json").chmod(0o644)
            execution_id = uuid4().hex
            run_started = time.monotonic()
            timings: list[dict[str, JsonValue]] = []
            timing_lock = Lock()
            recovery = None
            if operation == "run" and isinstance(job, JobManifest):
                from .decision_ledger import atomic_json

                recovery = checkpoint_dir or (
                    bundle.parent.parent
                    / "_runs"
                    / bundle.parent.name
                    / bundle.name
                    / ("checkpoint-" + execution_id)
                )
                identity = {
                    "bundle_digest": seal.digest,
                    "framework_digest": framework_digest,
                    "job": job.model_dump(mode="json"),
                }
                identity_path = recovery / "identity.json"
                if resume:
                    if (
                        not identity_path.exists()
                        or json.loads(identity_path.read_text()) != identity
                    ):
                        raise ValueError(
                            "Resume identity differs from current bundle/framework/job"
                        )
                    saved = recovery / "checkpoint.json"
                    if saved.exists():
                        (job_dir / "checkpoint.json").write_bytes(saved.read_bytes())
                else:
                    if recovery.exists():
                        raise ValueError("Checkpoint directory exists; use explicit resume")
                    atomic_json(identity_path, identity)
                concurrency = self.actor_settings.max_concurrency if self.actor_settings else 1
                (job_dir / "runtime.json").write_text(json.dumps({"max_concurrency": concurrency}))
                for staged in job_dir.iterdir():
                    staged.chmod(0o644)

            stage_starts: dict[str, float] = {}

            def progress(line: str) -> None:
                from .decision_ledger import atomic_json

                if line.startswith("HYPOTHESIS_CHECKPOINT:"):
                    if recovery is not None:
                        from simulation_core.checkpoint import merge_checkpoint

                        path = recovery / "checkpoint.json"
                        previous = json.loads(path.read_text()) if path.exists() else None
                        merged = merge_checkpoint(previous, json.loads(line.split(":", 1)[1]))
                        atomic_json(path, merged.model_dump(mode="json"))
                elif line.startswith("HYPOTHESIS_TIMING:"):
                    with timing_lock:
                        timings.append(json.loads(line.split(":", 1)[1]))
                        if recovery is not None:
                            atomic_json(recovery / ("timings-" + execution_id + ".json"), timings)
                else:
                    prefix = "HYPOTHESIS_WORKER_PROGRESS:"
                    if line.startswith(prefix):
                        event = json.loads(line[len(prefix) :])
                        stage = event["stage"]
                        if event["status"] == "started":
                            stage_starts[stage] = time.monotonic()
                        elif stage in stage_starts:
                            started = stage_starts.pop(stage)
                            timings.append(
                                {
                                    "stage": stage,
                                    "status": event["status"],
                                    "seconds": event.get("elapsed_seconds")
                                    or time.monotonic() - started,
                                }
                            )
                    self.report_progress(line)

            remote = f"/tmp/hypothesis-run-{uuid4().hex}"
            name = f"hypothesis-worker-{uuid4().hex}"
            exchange = None
            relay = None
            if self.actor_gateway is not None and isinstance(job, JobManifest):
                from .actor_relay import ActorRelay

                assert self.actor_model is not None
                actor_audit = (
                    bundle.parent.parent
                    / "_runs"
                    / bundle.parent.name
                    / bundle.name
                    / ("actors-" + uuid4().hex)
                )
                from .decision_ledger import DecisionLedger

                gateway = (
                    DecisionLedger(
                        self.actor_gateway,
                        recovery / "responses",
                        max_calls=self.actor_settings.call_budgets(job.simulation)[0]
                        if self.actor_settings
                        else 48,
                        max_calls_per_actor=self.actor_settings.call_budgets(job.simulation)[1]
                        if self.actor_settings
                        else 48,
                    )
                    if recovery
                    else self.actor_gateway
                )
                relay = ActorRelay(
                    gateway,
                    self.actor_model,
                    job,
                    actor_audit,
                    settings=self.actor_settings,
                )
                exchange = relay.exchange
            lease = None
            if recovery is not None:
                print(f"[worker] checkpoint directory: {recovery}", flush=True)
                descriptor = os.open(recovery / "run.lock", os.O_CREAT | os.O_RDWR, 0o600)
                lease = os.fdopen(descriptor, "w")
                try:
                    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    lease.close()
                    raise ValueError(
                        "This checkpoint is already in use by another worker"
                    ) from None
            try:
                mount = str(stage)
                if self.sandbox:
                    self._copy_to_sandbox(stage, remote)
                    mount = remote
                result = bounded_command(
                    self.run_arguments(
                        name, f"{mount}/bundle", f"{mount}/job", image, operation, seal.digest
                    ),
                    seconds=self.limits.wall_seconds,
                    max_bytes=self.limits.output_bytes,
                    exchange=exchange,
                    on_tick=relay.heartbeat if relay is not None else None,
                    on_stderr_line=progress,
                    exchange_workers=self.actor_settings.max_concurrency
                    if self.actor_settings
                    else 1,
                )
                if result.code:
                    raise RuntimeError(
                        f"Isolated worker failed ({result.code}): {result.stderr[-4000:]}"
                    )

                response = WorkerResponse.model_validate_json(result.stdout)
                if response.bundle_digest != seal.digest:
                    raise ValueError("Worker response refers to a different bundle")
                if response.result is not None and response.result.manifest != job:
                    raise ValueError("Worker returned a different experiment manifest")
                if response.tool_result is not None and response.tool_result.manifest != job:
                    raise ValueError("Worker returned a different tool manifest")
                if response.diagnostic is not None and response.diagnostic.result.manifest != job:
                    raise ValueError("Worker diagnostic refers to a different manifest")
                if (
                    operation == "run"
                    and response.result is not None
                    and manifest.notebook is not None
                    and response.notebook_json is None
                ):
                    raise ValueError("Worker omitted the required results notebook")
                if response.notebook_json is not None:
                    validate_notebook_json(response.notebook_json)
                if len(response.probe_results) != (
                    len(probes) if operation == "run" and response.result is not None else 0
                ):
                    raise ValueError("Unexpected probe result count")
                if any(
                    result.manifest != probe
                    for result, probe in zip(response.probe_results, probes)
                ):
                    raise ValueError("Worker returned a different probe manifest")
                receipt = RunReceipt(
                    elapsed_seconds=time.monotonic() - run_started,
                    checkpoint_directory=str(recovery) if recovery is not None else None,
                    timings=tuple(timings),
                    bundle_digest=seal.digest,
                    image_id=image,
                    framework_digest=framework_digest,
                    limits=self.limits,
                    operation=operation,
                    actor_api_attempts=0 if relay is None else relay.provider_attempts,
                    replayed_actor_requests=0 if relay is None else relay.replayed,
                    response=response,
                )
                reports = bundle.parent.parent / "_runs" / bundle.parent.name / bundle.name
                reports.mkdir(parents=True, exist_ok=True)
                run_id = uuid4().hex
                path = reports / f"{run_id}.json"
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w") as stream:
                    stream.write(receipt.model_dump_json(indent=2) + "\n")
                if response.notebook_json is not None:
                    export_notebook(response, reports / run_id)
                if response.diagnostic is not None:
                    export_diagnostic(response.diagnostic, reports / (run_id + "-unapproved"))
                return receipt
            finally:
                if recovery is not None:
                    from .decision_ledger import atomic_json

                    atomic_json(recovery / ("timings-" + execution_id + ".json"), timings)
                if lease is not None:
                    lease.close()
                subprocess.run(
                    self._docker("rm", "--force", name),
                    capture_output=True,
                    timeout=20,
                    check=False,
                )
                if self.sandbox:
                    subprocess.run(
                        [self.sbx, "exec", self.sandbox, "rm", "-rf", remote],
                        capture_output=True,
                        timeout=20,
                        check=False,
                    )

    def render(
        self,
        bundle: Path,
        document: JobManifest | JobResult,
        output: Path,
    ) -> ReportReceipt:
        """Offline preview or saved-result rendering, with no relay even on a live worker."""
        operation: Literal["preview", "report"] = (
            "preview" if isinstance(document, JobManifest) else "report"
        )
        manifest, original, _ = verify_bundle(bundle)
        if manifest.notebook is None:
            raise ValueError("Bundle has no reporting specification")
        if operation == "preview" and manifest.notebook.preview_generator is None:
            raise ValueError("Bundle has no preview generator")
        if output.exists():
            raise ValueError("Use a fresh reporting output directory")
        data = document.model_dump_json(indent=2)
        name = "hypothesis-report-" + uuid4().hex
        remote = "/tmp/hypothesis-report-" + uuid4().hex
        with TemporaryDirectory(prefix="hypothesis-report-") as temporary:
            root = Path(temporary)
            framework = copy_trusted_context(self.project, root / "context")
            image = self.image_id("hypothesis-worker:" + framework[:20])
            stage = root / "stage"
            stage.mkdir(mode=0o755)
            seal = snapshot_bundle(bundle, stage / "bundle")
            if seal != original:
                raise ValueError("Bundle changed before reporting")
            (stage / "job").mkdir(mode=0o755)
            filename = "manifest.json" if operation == "preview" else "result.json"
            path = stage / "job" / filename
            path.write_text(data)
            path.chmod(0o644)
            try:
                mount = str(stage)
                if self.sandbox:
                    self._copy_to_sandbox(stage, remote)
                    mount = remote
                result = bounded_command(
                    self.run_arguments(
                        name, mount + "/bundle", mount + "/job", image, operation, seal.digest
                    ),
                    seconds=self.limits.wall_seconds,
                    max_bytes=self.limits.output_bytes,
                )
                if result.code:
                    raise RuntimeError("Offline reporting failed: " + result.stderr[-4000:])
                response = ReportResponse.model_validate_json(result.stdout)
                if response.bundle_digest != seal.digest:
                    raise ValueError("Report response refers to a different bundle")
                if response.notebook_json is not None:
                    validate_notebook_json(response.notebook_json)
                    from simulation_core.reports import (
                        validate_explanatory_notebook,
                        validate_preview_notebook,
                    )

                    if (
                        isinstance(document, JobResult)
                        and manifest.notebook.report_version == "explanatory.v1"
                    ):
                        validate_explanatory_notebook(
                            response.notebook_json, document, executed=True
                        )
                    elif operation == "preview":
                        validate_preview_notebook(response.notebook_json)
                receipt = ReportReceipt(
                    operation=operation,
                    bundle_digest=seal.digest,
                    image_id=image,
                    framework_digest=framework,
                    input_sha256=hashlib.sha256(data.encode()).hexdigest(),
                    response=response,
                )
                output.mkdir(parents=True, mode=0o700)
                from .authoring import private_json

                private_json(output / "receipt.json", receipt.model_dump(mode="json"))
                if response.passed:
                    assert response.notebook_json is not None
                    notebook = "preview.ipynb" if operation == "preview" else "results.ipynb"
                    for label, content in ((notebook, response.notebook_json), (filename, data)):
                        descriptor = os.open(
                            output / label, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
                        )
                        with os.fdopen(descriptor, "w") as stream:
                            stream.write(content)
                return receipt
            finally:
                subprocess.run(
                    self._docker("rm", "--force", name),
                    capture_output=True,
                    timeout=20,
                    check=False,
                )
                if self.sandbox:
                    subprocess.run(
                        [self.sbx, "exec", self.sandbox, "rm", "-rf", remote],
                        capture_output=True,
                        timeout=20,
                        check=False,
                    )
