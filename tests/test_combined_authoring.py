"""Synthetic offline authoring contracts; never invoke a model or import bundle code."""

import json
from pathlib import Path

import pytest

from agent_tools.authoring import CodingAgent
from agent_tools.contracts import AuthoredCandidate, CandidateResponse, Implementation, SourceFile
from agent_tools.guide import write_starter
from agent_tools.planning import review_plan
from agent_tools.process import ProcessResult
from agent_tools.specs import (
    VALIDATION_CHECKS,
    CheckResult,
    ReportReceipt,
    ReportResponse,
    RunReceipt,
    WorkerResponse,
)
from agent_tools.workflow import run_authoring
from agent_tools.workspace import candidate_from_workspace, component_id
from extension_worker import author_check, muse
from simulation_core.model_gateway import FakeGateway
from simulation_core.request import ExperimentRequest

PROJECT = Path(__file__).resolve().parents[1]


def workspace(tmp_path, kind="agent_simulation"):
    root, inputs = tmp_path / "workspace", tmp_path / "inputs"
    write_starter(root, kind=kind, experiment_id="fresh")
    inputs.mkdir()
    task = {
        "stage": "author_candidate",
        "experiment_id": "fresh",
        "request": ExperimentRequest(
            hypothesis="Synthetic example", execution_kind=kind
        ).model_dump(mode="json"),
    }
    (inputs / "task.json").write_text(json.dumps(task))
    return root, inputs, task


@pytest.mark.parametrize("kind", ["agent_simulation", "tool"])
def test_executable_starter_collects_valid_metadata_without_importing_sources(tmp_path, kind):
    root, inputs, task = workspace(tmp_path, kind)
    candidate = candidate_from_workspace(root, task)
    assert candidate.plan.bundle.experiment_id == "fresh"
    assert (
        review_plan(
            PROJECT, ExperimentRequest.from_json_values(task["request"]), "fresh", candidate.plan
        )
        == ()
    )
    assert all(component.acceptance_tests for component in candidate.plan.bundle.components)
    assert component_id("fresh", "mechanism", "Sample") == "experimental.fresh.mechanism.sample.v1"
    assert all(
        "NotImplementedError" not in source.content for source in candidate.implementation.files
    )
    (root / "experiment_extension/__init__.py").write_text(
        'raise AssertionError("must not import on host")\n'
    )
    monkey = pytest.MonkeyPatch()
    monkey.setattr(muse, "ROOT", root)
    monkey.setattr(muse, "INPUTS", inputs)
    try:
        muse.assemble()
        assert (
            CandidateResponse.model_validate_json((root / "response.json").read_text()).candidate
            is not None
        )
    finally:
        monkey.undo()


def test_default_workflow_authors_one_complete_candidate_then_freezes_before_run(
    plan, artifact, tmp_path
):
    authored = AuthoredCandidate(
        plan=plan,
        implementation=Implementation(
            summary="Synthetic",
            files=(SourceFile(path="experiment_extension/__init__.py", content=""),),
        ),
    )
    stages = []

    def respond(request):
        stage = json.loads(request.input_json)["stage"]
        stages.append(stage)
        assert stage == "author_candidate"
        return CandidateResponse(candidate=authored, review=None).model_dump_json()

    agent = CodingAgent(PROJECT, FakeGateway(respond), "fake", tmp_path / "audit", max_calls=2)

    class Worker:
        calls = 0

        def render(self, candidate, job, output):
            return ReportReceipt(
                operation="preview",
                bundle_digest="d",
                image_id="i",
                framework_digest="f",
                input_sha256="h",
                response=ReportResponse(bundle_digest="d", notebook_json='{"cells":[]}'),
            )

        def execute(self, candidate, job, **kwargs):
            self.calls += 1
            freeze = json.loads((agent.audit / "candidate-freeze-1.json").read_text())
            assert freeze["candidate"]["implementation"]["summary"] == "Synthetic"
            assert (agent.audit / "frozen_request.json").exists()
            return RunReceipt(
                bundle_digest="d",
                image_id="i",
                framework_digest="f",
                operation="run",
                response=WorkerResponse(
                    bundle_digest="d",
                    checks=tuple(
                        CheckResult(name=name, passed=True, exit_code=0, output="Synthetic")
                        for name in VALIDATION_CHECKS
                    ),
                    result=artifact.model_copy(update={"manifest": job}),
                ),
            )

    worker = Worker()
    outcome = run_authoring(
        agent, ExperimentRequest(hypothesis="Synthetic"), "fresh", tmp_path / "fresh", worker
    )
    assert outcome.status == "completed" and worker.calls == 1
    assert stages == ["author_candidate"]


def test_author_check_cache_is_selective_and_failure_cannot_leave_stale_response(
    tmp_path, monkeypatch
):
    root, inputs, _task = workspace(tmp_path)
    monkeypatch.setattr(author_check, "require_container", lambda: None)
    commands = []
    fail_types = [False]
    monkeypatch.setenv("HYPOTHESIS_ACTOR_RELAY", "/synthetic-live-relay.sock")
    monkeypatch.setenv("API_KEY_2", "synthetic-only")

    def command(args, **kwargs):
        assert "HYPOTHESIS_ACTOR_RELAY" not in kwargs["env"]
        assert "API_KEY_2" not in kwargs["env"]
        commands.append(args)
        if "mypy" in args and fail_types[0]:
            return ProcessResult(1, "named type failure", "")
        return ProcessResult(0, "Synthetic subprocess success; not executed", "")

    monkeypatch.setattr(author_check, "bounded_command", command)
    first = author_check.run_author_checks(root, inputs, PROJECT)
    assert first.ready and (root / "response.json").exists()
    count = len(commands)
    second = author_check.run_author_checks(root, inputs, PROJECT)
    assert second.ready and all(result.cached for result in second.results)
    assert len(commands) == count
    # Test-only edits invalidate lint/tests/metadata, but not types or preview.
    path = root / "tests/test_signal.py"
    path.write_text(path.read_text() + "\n# a new test note\n")
    third = author_check.run_author_checks(root, inputs, PROJECT)
    assert third.ready
    assert next(result for result in third.results if result.name == "types").cached
    assert next(result for result in third.results if result.name == "preview").cached
    fail_types[0] = True
    source = root / "experiment_extension/component.py"
    source.write_text(source.read_text() + "\n# changed code\n")
    fourth = author_check.run_author_checks(root, inputs, PROJECT, only=("types",))
    assert not fourth.ready
    assert not (root / "response.json").exists()
    assert "experiment_extension/component.py" in fourth.changed_files
    assert (
        next(result for result in fourth.results if result.name == "types").output
        == "named type failure"
    )


def test_author_check_requires_container_before_any_subprocess(tmp_path, monkeypatch):
    monkeypatch.setattr(
        author_check,
        "require_container",
        lambda: (_ for _ in ()).throw(RuntimeError("container required")),
    )
    monkeypatch.setattr(
        author_check, "bounded_command", lambda *a, **k: pytest.fail("Host code execution")
    )
    with pytest.raises(RuntimeError, match="container required"):
        author_check.run_author_checks(tmp_path, tmp_path, PROJECT)


def test_report_only_repair_rejects_scientific_edits_without_poisoning_baseline(
    plan, artifact, tmp_path
):
    from agent_tools.contracts import NotebookReview

    calls = []
    initial = AuthoredCandidate(
        plan=plan,
        implementation=Implementation(
            summary="Synthetic",
            files=(
                SourceFile(path="experiment_extension/__init__.py", content=""),
                SourceFile(path="experiment_extension/reporting.py", content="value = 1\n"),
                SourceFile(path="experiment_extension/science.py", content="value = 1\n"),
            ),
        ),
    )
    reviews = [0]
    author_calls = [0]

    def respond(request):
        task = json.loads(request.input_json)
        calls.append(task["stage"])
        if task["stage"] == "review_notebook":
            reviews[0] += 1
            return NotebookReview(
                approved=reviews[0] > 1,
                issues=() if reviews[0] > 1 else ("Explain the recorded result",),
            ).model_dump_json()
        author_calls[0] += 1
        if author_calls[0] == 1:
            candidate = initial
        else:
            assert task["repair_scope"] == "report_only"
            previous = task["previous_candidate"]["implementation"]["files"]
            assert (
                next(f["content"] for f in previous if f["path"].endswith("science.py")).strip()
                == "value = 1"
            )
            candidate = initial.model_copy(
                update={
                    "implementation": initial.implementation.model_copy(
                        update={
                            "files": tuple(
                                f.model_copy(update={"content": "value = 2\n"})
                                if f.path.endswith("reporting.py")
                                or (author_calls[0] == 2 and f.path.endswith("science.py"))
                                else f
                                for f in initial.implementation.files
                            )
                        }
                    )
                }
            )
        return CandidateResponse(candidate=candidate, review=None).model_dump_json()

    agent = CodingAgent(
        PROJECT, FakeGateway(respond), "fake", tmp_path / "audit", content_review=True, max_calls=8
    )

    class Worker:
        count = 0

        def render(self, candidate, job, output):
            return ReportReceipt(
                operation="preview",
                bundle_digest="d",
                image_id="i",
                framework_digest="f",
                input_sha256="h",
                response=ReportResponse(bundle_digest="d", notebook_json='{"cells":[]}'),
            )

        def execute(self, candidate, job, **kwargs):
            self.count += 1
            return RunReceipt(
                bundle_digest="d",
                image_id="i",
                framework_digest="f",
                operation="run",
                response=WorkerResponse(
                    bundle_digest="d",
                    checks=tuple(
                        CheckResult(name=n, passed=True, exit_code=0, output="synthetic")
                        for n in VALIDATION_CHECKS
                    ),
                    result=artifact.model_copy(update={"manifest": job}),
                ),
            )

    worker = Worker()
    result = run_authoring(
        agent, ExperimentRequest(hypothesis="Synthetic"), "fresh", tmp_path / "fresh", worker
    )
    assert result.status == "completed" and worker.count == 1
    assert author_calls[0] == 3
    assert "plan_and_tests" not in calls and "implementation" not in calls


def test_check_diagnostics_are_exportable_as_data_before_workspace_cleanup(tmp_path):
    from extension_worker.muse import author_check_evidence

    directory = tmp_path / ".author-check"
    directory.mkdir()
    latest = {
        "ready": True,
        "seconds": 0.01,
        "results": [
            {
                "name": "tests",
                "passed": True,
                "cached": True,
                "seconds": 0.0,
                "output": "diagnostic",
            }
        ],
    }
    (directory / "report.json").write_text(json.dumps(latest))
    first = {**latest, "seconds": 2.0, "changed_files": ["experiment_extension/component.py"]}
    (directory / "history.jsonl").write_text(json.dumps(first) + "\n" + json.dumps(latest) + "\n")
    data = author_check_evidence(tmp_path)
    assert data["latest"] == latest
    assert [row["seconds"] for row in data["recent_invocations"]] == [2.0, 0.01]
    assert "output" not in data["recent_invocations"][0]["checks"][0]
