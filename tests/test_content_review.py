"""Editorial review and repeated-game budgets never cause live reexecution."""

import json
from pathlib import Path

import pytest

from agent_tools.authoring import CodingAgent
from agent_tools.contracts import (
    Implementation,
    ImplementationResponse,
    NotebookReview,
    PlanningResponse,
    SourceFile,
)
from agent_tools.execution_settings import ActorExecutionSettings
from agent_tools.specs import (
    VALIDATION_CHECKS,
    CheckResult,
    ReportReceipt,
    ReportResponse,
    RunReceipt,
    WorkerResponse,
)
from agent_tools.workflow import run_authoring
from simulation_core.execution import JobManifest
from simulation_core.model_gateway import FakeGateway
from simulation_core.reports import assumption_prose
from simulation_core.request import ExperimentRequest
from simulation_core.types import Assumption

PROJECT = Path(__file__).resolve().parents[1]


def test_prose_omits_raw_values():
    item = Assumption(
        path="/permissions",
        value=["private_field"],
        source="user",
        rationale="Participants see only their own information.",
    )
    result = assumption_prose((item,))
    assert result == ("Participants see only their own information (user requirement).",)
    assert "private_field" not in result[0]


def test_budget_counts_all_rounds_and_reserves_retries(plan):
    world = plan.simulation.world
    actors = tuple(
        world.actors[0].model_copy(update={"id": str(i), "policy_id": "llm.v1"}) for i in range(5)
    )
    config = plan.simulation.model_copy(
        update={
            "world": world.model_copy(update={"actors": actors}),
            "protocol_parameters": {"rounds": 10},
        }
    )
    with pytest.raises(ValueError, match="requires 100"):
        ActorExecutionSettings(model="model", max_total_calls=48).validate_budget(config)
    ActorExecutionSettings(model="model").validate_budget(config)
    assert ActorExecutionSettings(model="model").call_budgets(config)[0] == 100
    ActorExecutionSettings(model="model", max_total_calls=100).validate_budget(config)


@pytest.mark.parametrize("change_scientific_source", [False, True])
def test_content_repair_keeps_original_simulation_and_does_not_call_actors_again(
    plan, artifact, tmp_path, change_scientific_source
):
    reviewed = 0

    def source(repaired=False):
        return Implementation(
            summary="Synthetic source",
            files=(
                SourceFile(
                    path="experiment_extension/__init__.py",
                    content="x=2\n" if repaired and change_scientific_source else "",
                ),
                SourceFile(
                    path="experiment_extension/reporting.py",
                    content="quality=1\n" if repaired else "quality=0\n",
                ),
            ),
        )

    def respond(request):
        nonlocal reviewed
        task = json.loads(request.input_json)
        if task["stage"] == "plan_and_tests":
            return PlanningResponse(plan=plan, review=None).model_dump_json()
        if task["stage"] == "review_notebook":
            if not task["observed"]:
                return NotebookReview(approved=True).model_dump_json()
            reviewed += 1
            return NotebookReview(
                approved=reviewed > 1,
                issues=() if reviewed > 1 else ("Remove the table repetition",),
            ).model_dump_json()
        return ImplementationResponse(
            implementation=source("validation_feedback" in task), review=None
        ).model_dump_json()

    agent = CodingAgent(
        PROJECT,
        FakeGateway(respond),
        "fake",
        tmp_path / "audit",
        content_review=True,
        combined_authoring=False,
    )

    class Worker:
        calls = 0
        renders = 0

        def render(self, candidate, document, output):
            self.renders += 1
            return ReportReceipt(
                operation="preview" if isinstance(document, JobManifest) else "report",
                bundle_digest="d",
                image_id="i",
                framework_digest="f",
                input_sha256="h",
                response=ReportResponse(bundle_digest="d", notebook_json='{"cells":[]}'),
            )

        def execute(self, candidate, job, **kwargs):
            self.calls += 1
            return RunReceipt(
                bundle_digest="d",
                image_id="i",
                framework_digest="f",
                operation="run",
                actor_api_attempts=3,
                response=WorkerResponse(
                    bundle_digest="d",
                    checks=tuple(
                        CheckResult(name=n, passed=True, exit_code=0, output="ok")
                        for n in sorted(VALIDATION_CHECKS)
                    ),
                    result=artifact.model_copy(update={"manifest": job}),
                    notebook_json='{"cells":[]}',
                ),
            )

    worker = Worker()
    outcome = run_authoring(
        agent, ExperimentRequest(hypothesis="Test"), "fresh", tmp_path / "fresh", worker
    )
    assert worker.calls == 1
    if change_scientific_source:
        assert outcome.status == "needs_review" and worker.renders == 1
    else:
        assert outcome.status == "completed" and worker.renders == 2
        assert outcome.report_candidate.endswith("/v2") and outcome.candidate.endswith("/v1")
        assert outcome.report_receipt.actor_api_calls == 0


def test_trajectory_marker_requires_existing_category():
    from pydantic import ValidationError

    from simulation_core.reports import ChartSeries, ReportFigure, ReportMarker

    chart = ReportFigure(
        title="Time series",
        ylabel="Amount",
        kind="line",
        categories=("1", "2"),
        series=(ChartSeries(label="Observed", values=(1.0, 2.0)),),
        markers=(ReportMarker(category="2", label="Intervention"),),
    )
    assert chart.markers[0].position == "before"
    with pytest.raises(ValidationError, match="displayed category"):
        ReportFigure(
            title="Invalid",
            ylabel="Amount",
            categories=("1",),
            series=(ChartSeries(label="Data", values=(1.0,)),),
            markers=(ReportMarker(category="2", label="Missing"),),
        )
