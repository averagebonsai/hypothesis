"""Offline checks: synthetic artifacts only, no coding API or experimental execution."""

import json
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

from agent_tools.authoring import CodingAgent, Implementation, SourceFile, materialize
from agent_tools.contracts import ImplementationResponse, PlanningResponse
from agent_tools.notebooks import export_notebook, validate_notebook_json
from agent_tools.planning import review_plan
from agent_tools.specs import (
    VALIDATION_CHECKS,
    CheckResult,
    NotebookSpec,
    RunReceipt,
    WorkerLimits,
    WorkerResponse,
)
from agent_tools.verification import independent_optimum, verify_problem_result
from agent_tools.workflow import run_authoring
from simulation_core.execution import JobResult
from simulation_core.model_gateway import FakeGateway
from simulation_core.problems import (
    ConstraintSpec,
    ObjectiveSpec,
    Operation,
    ProblemStatement,
    Reference,
    VariableSpec,
)
from simulation_core.reporting import write_results_notebook
from simulation_core.request import ExperimentRequest
from simulation_core.types import (
    Action,
    Outcome,
    SimulationConfig,
)

PROJECT = Path(__file__).resolve().parents[1]


def test_plan_reviews_bindings_lint_and_component_exercising_before_freeze(plan):
    request = ExperimentRequest(hypothesis="Synthetic request")
    assert not review_plan(PROJECT, request, "fresh", plan)
    copied_formula = plan.model_copy(
        update={
            "tests": (
                SourceFile(
                    path="tests/test_payload.py",
                    content="def test_payload():\n    assert sum([1, 2]) == 3\n",
                ),
            )
        }
    )
    assert any(
        "exercise an exported component" in issue
        for issue in review_plan(PROJECT, request, "fresh", copied_formula)
    )
    broken_import = plan.model_copy(
        update={
            "tests": (
                SourceFile(
                    path="tests/test_payload.py",
                    content="import math\n" + plan.tests[0].content,
                ),
            )
        }
    )
    assert any(
        "Test lint failed" in issue
        for issue in review_plan(PROJECT, request, "fresh", broken_import)
    )
    config = plan.simulation.model_dump(mode="json")
    config["mechanism_id"] = "missing"
    wrong = plan.model_copy(update={"simulation": SimulationConfig.from_json_values(config)})
    assert any(
        "Unknown mechanism" in issue for issue in review_plan(PROJECT, request, "fresh", wrong)
    )
    assert "experiment_extension.payload" not in sys.modules


def test_materialize_retains_versions_after_more_than_two_repairs(plan, tmp_path):
    implementation = Implementation(
        summary="No host imports",
        files=(
            SourceFile(
                path="experiment_extension/__init__.py",
                content='raise RuntimeError("never import")\n',
            ),
        ),
    )
    for version in range(1, 6):
        root = tmp_path / f"v{version}"
        materialize(root, ExperimentRequest(hypothesis="Synthetic"), plan, implementation, version)
    assert json.loads((tmp_path / "v5/bundle.json").read_text())["repair_counts"] == {
        "implementation_validation": 4
    }
    assert (tmp_path / "v1/experiment_extension/__init__.py").exists()


def test_independent_verification_rejects_wrong_scores_and_wrong_benchmark(artifact, verification):
    verify_problem_result(artifact, verification)
    problem = artifact.manifest.request.problem
    assert independent_optimum(problem, {"x": 1.0}) == pytest.approx(0.0, abs=1e-10)
    event = artifact.result.events[0].model_copy(
        update={"outcome": Outcome(payoffs={"worker": 99.0})}
    )
    wrong = artifact.model_copy(
        update={"result": artifact.result.model_copy(update={"events": (event,)})}
    )
    with pytest.raises(ValueError, match="Objective mismatch"):
        verify_problem_result(wrong, verification)
    solution = artifact.benchmark.result.equilibria[0].model_copy(
        update={
            "actions": (Action(actor_id="worker", kind="submit", payload={"x": 2.0}),),
            "outcome": Outcome(payoffs={"worker": -1.0}),
        }
    )
    wrong_benchmark = artifact.benchmark.model_copy(
        update={"result": artifact.benchmark.result.model_copy(update={"equilibria": (solution,)})}
    )
    with pytest.raises(ValueError, match="independent numerical reference"):
        verify_problem_result(
            artifact.model_copy(update={"benchmark": wrong_benchmark}), verification
        )


def test_notebook_generation_and_export_are_data_only(artifact, tmp_path):
    path = write_results_notebook(artifact, tmp_path / "generated")
    validate_notebook_json(path.read_text())
    notebook = json.loads(path.read_text())
    assert all(cell.get("execution_count") is None for cell in notebook["cells"])
    assert "JobResult.model_validate_json" in notebook["cells"][1]["source"]
    response = WorkerResponse(
        bundle_digest="synthetic",
        checks=tuple(
            CheckResult(name=name, passed=True, exit_code=0, output="Synthetic")
            for name in sorted(VALIDATION_CHECKS)
        ),
        result=artifact,
        notebook_json=path.read_text(),
    )
    export_notebook(response, tmp_path / "exported")
    assert (tmp_path / "exported/results.ipynb").stat().st_mode & 0o777 == 0o600
    assert (
        JobResult.model_validate_json((tmp_path / "exported/result.json").read_text()) == artifact
    )


@pytest.mark.skipif(
    not Path("/.dockerenv").exists() or os.geteuid() != 10001,
    reason="Notebook execution stays inside the isolated worker",
)
def test_notebook_executes_inside_worker_from_synthetic_result(artifact, monkeypatch):
    from extension_worker.reporting import execute_report

    # Trusted test shim, not a generated experiment or a simulation run.
    module = ModuleType("experiment_extension.reporting")
    module.write_notebook = write_results_notebook
    monkeypatch.setitem(sys.modules, module.__name__, module)
    content = execute_report(
        artifact, NotebookSpec(generator="experiment_extension.reporting:write_notebook")
    )
    notebook = json.loads(content)
    assert all(
        cell["execution_count"] is not None
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
    )
    assert any(cell.get("outputs") for cell in notebook["cells"])


@pytest.mark.parametrize(
    "target,budget,expected", [((4.0, 2.0), 3.0, 4.5), ((7.0, -4.0), 2.0, 41.0)]
)
def test_independent_reference_supports_coupled_vector_constraints(target, budget, expected):
    problem = ProblemStatement(
        description="Synthetic constrained vector loss",
        evaluation="deterministic",
        parameters={"desired": target, "capacity": budget},
        variables=(VariableSpec(name="choice", shape="vector", dimension="desired", lower=0.0),),
        objectives=(
            ObjectiveSpec(
                name="loss",
                sense="minimize",
                expression=Operation(
                    operator="sum",
                    arguments=(
                        Operation(
                            operator="square",
                            arguments=(
                                Operation(
                                    operator="subtract",
                                    arguments=(Reference(name="choice"), Reference(name="desired")),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
        constraints=(
            ConstraintSpec(
                name="cap",
                relation="eq",
                left=Operation(operator="sum", arguments=(Reference(name="choice"),)),
                right=Reference(name="capacity"),
            ),
        ),
    )
    assert independent_optimum(problem, {"choice": (budget / 2, budget / 2)}) == pytest.approx(
        expected, abs=1e-6
    )


@pytest.mark.parametrize("framework_failure", [False, True])
def test_workflow_repairs_beyond_old_limits_with_only_fake_transports(
    plan, artifact, tmp_path, framework_failure
):
    implementation = Implementation(
        summary="Synthetic source, never imported",
        files=(
            SourceFile(
                path="experiment_extension/__init__.py",
                content='raise RuntimeError("never import")\n',
            ),
        ),
    )
    gateway = FakeGateway(
        lambda request: (
            PlanningResponse(plan=plan, review=None).model_dump_json()
            if json.loads(request.input_json)["stage"] == "plan_and_tests"
            else ImplementationResponse(
                implementation=implementation, review=None
            ).model_dump_json()
        )
    )
    agent = CodingAgent(
        PROJECT, gateway, "fake-model", tmp_path / "audit", max_calls=8, combined_authoring=False
    )

    class FakeWorker:
        calls = 0

        def render(self, candidate, job, output):
            from agent_tools.specs import ReportReceipt, ReportResponse

            return ReportReceipt(
                operation="preview",
                bundle_digest="synthetic",
                image_id="synthetic",
                framework_digest="synthetic",
                input_sha256="synthetic",
                response=ReportResponse(bundle_digest="synthetic", notebook_json="synthetic"),
            )

        def execute(self, candidate, job, **kwargs):
            self.calls += 1
            passed = self.calls == 5
            return RunReceipt(
                bundle_digest="synthetic",
                image_id="synthetic",
                framework_digest="synthetic",
                limits=WorkerLimits(),
                operation="run",
                response=WorkerResponse(
                    bundle_digest="synthetic",
                    checks=tuple(
                        CheckResult(
                            name=name,
                            passed=passed or (name == "regressions" and not framework_failure),
                            exit_code=0
                            if passed or (name == "regressions" and not framework_failure)
                            else 1,
                            output="Synthetic transport result",
                        )
                        for name in sorted(VALIDATION_CHECKS)
                    ),
                    result=artifact.model_copy(update={"manifest": job}) if passed else None,
                ),
            )

    worker = FakeWorker()
    progress = []
    receipt = run_authoring(
        agent,
        ExperimentRequest(hypothesis="Synthetic"),
        "fresh",
        tmp_path / "fresh",
        worker,
        progress=progress.append,
    )
    if framework_failure:
        assert receipt.status == "needs_review"
        assert receipt.review.affected_contracts == ("toolkit_regressions",)
        assert worker.calls == 1 and agent.gateway.calls == 2
        return
    assert receipt.receipt.response.result is not None
    assert worker.calls == 5 and agent.gateway.calls == 6
    assert (tmp_path / "fresh/v1/bundle.lock.json").exists()
    assert (
        json.loads((tmp_path / "fresh/v5/bundle.json").read_text())["repair_counts"][
            "implementation_validation"
        ]
        == 4
    )
    assert progress


def test_static_review_tracks_shared_component_instances_and_aliases(plan):
    from agent_tools.planning import test_structure_issues as inspect_tests

    sources = {
        "tests/test_payload.py": """
from experiment_extension.payload import Payload
SHARED = Payload(value=2)
ALIAS = SHARED

def test_payload():
    assert ALIAS.value == 2
"""
    }
    assert inspect_tests(sources, plan.bundle) == []
