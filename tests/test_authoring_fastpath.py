"""Authoring speed changes retain offline and single-live-run boundaries."""

import ast
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_tools.authoring import CodingAgent
from agent_tools.contracts import (
    Implementation,
    ImplementationResponse,
    PlanningResponse,
    SourceFile,
)
from agent_tools.docker_worker import DockerWorker
from agent_tools.execution_settings import ActorExecutionSettings
from agent_tools.guide import interface_guide, write_starter
from agent_tools.specs import (
    VALIDATION_CHECKS,
    CheckResult,
    ReportReceipt,
    ReportResponse,
    RunReceipt,
    WorkerResponse,
)
from agent_tools.workflow import run_authoring
from simulation_core.model_gateway import FakeGateway
from simulation_core.reports import ReportPreview, validate_preview_notebook, write_preview_notebook
from simulation_core.request import ExperimentRequest

PROJECT = Path(__file__).resolve().parents[1]


def test_operator_settings_resolve_transport_and_preserve_scientific_instructions(plan):
    config = plan.simulation
    actor = config.world.actors[0].model_copy(
        update={
            "policy_id": "llm.v1",
            "policy_parameters": {
                "model": "wrong",
                "max_output_tokens": 1000,
                "instructions": "Act on private information",
                "persona": "cautious",
            },
        }
    )
    config = config.model_copy(
        update={"world": config.world.model_copy(update={"actors": (actor,)})}
    )
    settings = ActorExecutionSettings(model="actor-model", max_output_tokens=3000)
    resolved = settings.resolve(config)
    values = resolved.world.actors[0].policy_parameters
    assert values["model"] == "actor-model" and values["max_output_tokens"] == 3000
    assert (
        values["instructions"] == "Act on private information" and values["persona"] == "cautious"
    )
    assert config.world.actors[0].policy_parameters["model"] == "wrong"
    with pytest.raises(ValidationError):
        ActorExecutionSettings(model="actor", max_output_tokens=0)


def test_guide_and_starter_are_small_domain_neutral_and_do_not_overwrite(tmp_path):
    text = interface_guide()
    assert "validate_actions" in text and "numerical_nash.v1" in text
    assert "coupled vector" in text and "pending" in text
    assert len(text) < 24000
    write_starter(tmp_path)
    for file in tmp_path.rglob("*.py"):
        ast.parse(file.read_text())
    with pytest.raises(FileExistsError):
        write_starter(tmp_path)


def test_preview_has_theory_and_pending_observations_but_no_result_interface(tmp_path):
    preview = ReportPreview(
        title="A problem",
        background="Rules",
        rationale="Question",
        theory="The reference is calculated from the input parameters.",
        assumptions=("A stated condition",),
        limitations=("No observed performance yet",),
    )
    path = write_preview_notebook(tmp_path, preview)
    validate_preview_notebook(path.read_text())
    notebook = json.loads(path.read_text())
    assert "hypothesis_report" not in notebook["metadata"]
    assert "Observed results and their interpretation are pending" in path.read_text()
    with pytest.raises(ValidationError):
        ReportPreview.model_validate(
            {**preview.model_dump(), "interpretation": "Actors will perform well"}
        )


def test_report_transport_never_enables_actor_relay_even_on_live_worker(tmp_path):
    worker = DockerWorker(tmp_path, actor_gateway=FakeGateway(lambda _: ""), actor_model="actor")
    for operation in ("preview", "report"):
        args = worker.run_arguments(
            "test", "/bundle-input", "/job-input", "image", operation, "digest"
        )
        assert "HYPOTHESIS_ENABLE_ACTORS=1" not in args and "--interactive" not in args
        assert args[args.index("--network") + 1] == "none"
        assert "extension_worker.reporting" in args


@pytest.mark.parametrize("run_passed", [True, False])
@pytest.mark.parametrize("preview_fails_once", [True, False])
def test_workflow_completes_once_or_stops_after_live_failure_without_reexecution(
    plan, artifact, tmp_path, run_passed, preview_fails_once
):
    implementation = Implementation(
        summary="data only",
        files=(SourceFile(path="experiment_extension/__init__.py", content=""),),
    )
    requests = []

    def respond(request):
        stage = json.loads(request.input_json)["stage"]
        requests.append(stage)
        if stage == "plan_and_tests":
            return PlanningResponse(plan=plan, review=None).model_dump_json()
        return ImplementationResponse(implementation=implementation, review=None).model_dump_json()

    agent = CodingAgent(PROJECT, FakeGateway(respond), "fake", tmp_path / "audit")

    class Worker:
        runs = 0
        previews = 0

        def render(self, candidate, job, output):
            self.previews += 1
            return ReportReceipt(
                operation="preview",
                bundle_digest="d",
                image_id="i",
                framework_digest="f",
                input_sha256="h",
                response=ReportResponse(bundle_digest="d", error="Preview needs repair")
                if preview_fails_once and self.previews == 1
                else ReportResponse(bundle_digest="d", notebook_json="preview"),
            )

        def execute(self, candidate, job, **kwargs):
            assert self.previews == (2 if preview_fails_once else 1)
            self.runs += 1
            return RunReceipt(
                bundle_digest="d",
                image_id="i",
                framework_digest="f",
                operation="run",
                actor_api_attempts=3,
                response=WorkerResponse(
                    bundle_digest="d",
                    checks=tuple(
                        CheckResult(name=name, passed=True, exit_code=0, output="ok")
                        for name in sorted(VALIDATION_CHECKS)
                    ),
                    result=artifact.model_copy(update={"manifest": job}) if run_passed else None,
                    error=None if run_passed else "report failed",
                ),
            )

    worker = Worker()
    outcome = run_authoring(
        agent, ExperimentRequest(hypothesis="Test"), "fresh", tmp_path / "fresh", worker
    )
    assert worker.runs == 1 and worker.previews == (2 if preview_fails_once else 1)
    assert requests == ["plan_and_tests", "implementation"] + (
        ["repair_implementation"] if preview_fails_once else []
    )
    assert outcome.status == ("completed" if run_passed else "needs_review")


def test_preview_kernel_execution_is_container_only(tmp_path, monkeypatch):
    import os

    from agent_tools.specs import NotebookSpec
    from extension_worker import reporting

    if not Path("/.dockerenv").exists() or os.geteuid() != 10001:
        pytest.skip("Notebook kernels run only in isolated Docker")

    preview = ReportPreview(
        title="Theory",
        background="Definition",
        rationale="Purpose",
        theory="A calculated reference",
        assumptions=("Condition",),
        limitations=("No observations",),
    )
    # Patch a trusted function in-process; no generated package imports on host.
    import sys
    from types import ModuleType

    module = ModuleType("experiment_extension.report")
    module.generate = lambda job, directory: write_preview_notebook(directory, preview)
    monkeypatch.setitem(sys.modules, "experiment_extension.report", module)
    from simulation_core.execution import JobManifest
    from simulation_core.types import SimulationConfig

    config = SimulationConfig.model_validate_json(
        (PROJECT / "src/examples/configs/measurements.json").read_text()
    )
    content = reporting.execute_preview(
        JobManifest(request=ExperimentRequest(hypothesis="Question"), simulation=config),
        NotebookSpec(
            generator="experiment_extension.report:generate",
            preview_generator="experiment_extension.report:generate",
        ),
    )
    assert '"execution_count": 1' in content
