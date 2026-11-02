"""Native contracts, routing and deterministic checks; no live model requests."""

import io
import json
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest
from pydantic import ValidationError
from test_problems import problem

from agent_tools.authoring import CodingAgent, materialize
from agent_tools.checks import invalid_assignments, standard_checks
from agent_tools.contracts import CodingPlan, PlanningResponse, ReviewRequest
from agent_tools.jobs import ToolInvocation, ToolJobManifest
from agent_tools.notebooks import export_diagnostic
from agent_tools.planning import review_plan
from agent_tools.specs import DiagnosticArtifact, ReferenceCase, WorkerResponse
from agent_tools.test_intent import fixture_issues
from agent_tools.workflow import run_authoring
from components.gateways.live import configured_coding_gateway, configured_gateway
from components.gateways.openai import native_schema
from components.gateways.settings import LiveModelSettings
from simulation_core.model_gateway import FakeGateway
from simulation_core.request import ExperimentRequest

PROJECT = Path(__file__).resolve().parents[1]


def test_native_documents_reject_embedded_json_strings(plan):
    assert CodingPlan.model_validate_json(plan.model_dump_json()) == plan
    data = plan.model_dump(mode="json")
    data["bundle"] = json.dumps(data["bundle"])
    with pytest.raises(ValidationError):
        CodingPlan.model_validate_json(json.dumps(data))
    schema = native_schema(PlanningResponse.model_json_schema())
    assert "#/$defs/JsonValue" not in json.dumps(schema)
    assert "bundle_json" not in json.dumps(schema)
    assert schema["$defs"]["CodingPlan"]["properties"]["bundle"]["$ref"].endswith("/BundleManifest")


def test_coding_http_request_uses_full_model_max_and_native_schema(monkeypatch, tmp_path):
    from agent_tools.authoring import AuthoringReviewRequired
    from components.gateways import openai
    from components.gateways.meta import MetaResponsesGateway

    def fake_urlopen(request, timeout):
        body = json.loads(request.data)
        assert body["model"] == "muse-spark-1.3"
        assert body["reasoning"] == {"effort": "max"}
        assert body["text"]["format"]["strict"] is False
        assert "bundle_json" not in json.dumps(body["text"]["format"]["schema"])
        assert "#/$defs/JsonValue" not in json.dumps(body["text"]["format"]["schema"])
        response = PlanningResponse(
            plan=None,
            review=ReviewRequest(
                status="unsupported",
                reason="Synthetic capability gap",
                affected_contracts=("worker",),
            ),
        )
        return io.BytesIO(
            json.dumps(
                {
                    "status": "completed",
                    "model": body["model"],
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {"type": "output_text", "text": response.model_dump_json()}
                            ],
                        }
                    ],
                }
            ).encode()
        )

    monkeypatch.setattr(openai, "urlopen", fake_urlopen)
    gateway = MetaResponsesGateway("fake", frozenset({"muse-spark-1.3"}))
    agent = CodingAgent(PROJECT, gateway, "muse-spark-1.3", tmp_path / "audit")
    with pytest.raises(AuthoringReviewRequired):
        agent.plan(ExperimentRequest(hypothesis="Synthetic"), "fresh")


def test_review_is_terminal_before_another_model_or_worker_call(tmp_path):
    review = ReviewRequest(
        status="needs_review",
        reason="Conflicting frozen scientific expectations",
        affected_contracts=("test_expected_score",),
    )
    gateway = FakeGateway(
        lambda request: PlanningResponse(plan=None, review=review).model_dump_json()
    )
    agent = CodingAgent(PROJECT, gateway, "fake-model", tmp_path / "audit", max_calls=2)

    class NoWorker:
        def execute(self, *args, **kwargs):
            pytest.fail("Review must not execute a worker")

    outcome = run_authoring(
        agent,
        ExperimentRequest(hypothesis="Synthetic"),
        "fresh",
        tmp_path / "fresh",
        NoWorker(),
        progress=lambda _: None,
    )
    assert outcome.status == "needs_review" and outcome.review == review
    assert agent.gateway.calls == 1
    assert not (tmp_path / "fresh").exists()


def test_model_roles_are_separate_and_coding_requests_max(monkeypatch, tmp_path):
    monkeypatch.setenv("API_KEY", "fake-secret")
    monkeypatch.setenv("MODEL", "muse-spark-1.3-contributor")
    monkeypatch.setenv("MODEL_CODING", "muse-spark-1.3")
    actor_model, actor_gateway = configured_gateway()
    coding_model, coding_gateway = configured_coding_gateway()
    assert actor_model == "muse-spark-1.3-contributor"
    assert coding_model == "muse-spark-1.3"
    assert actor_gateway.allowed_models == frozenset({actor_model})
    assert coding_gateway.allowed_models == frozenset({coding_model})
    agent = CodingAgent.from_environment(PROJECT, tmp_path / "live-construction")
    assert agent.model == coding_model and agent.reasoning_effort == "max"
    assert agent.gateway.calls == 0
    monkeypatch.delenv("MODEL_CODING")
    with pytest.raises(ValueError, match="MODEL_CODING"):
        LiveModelSettings.load(role="coding", env_file=tmp_path / "missing")


def test_core_fixture_and_wrong_reference_expectations_rejected_before_freeze(
    plan, artifact, verification
):
    source = 'from simulation_core.types import WorldConfig\n\ndef fixture():\n    return WorldConfig.model_validate({"actors": []})\n'
    assert any("strict tuple" in issue for issue in fixture_issues(source, "fixture.py"))
    verification = verification.model_copy(
        update={
            "reference_cases": (
                ReferenceCase(
                    id="wrong", assignments={"x": 1.0}, feasible=True, objectives={"loss": 999.0}
                ),
            )
        }
    )
    candidate = plan.model_copy(
        update={
            "simulation": artifact.manifest.simulation,
            "bundle": plan.bundle.model_copy(update={"verification": verification}),
        }
    )
    assert any(
        "objective loss contradicts" in issue
        for issue in review_plan(PROJECT, artifact.manifest.request, "fresh", candidate)
    )


def test_rejection_cases_are_derived_from_actual_constraints():
    statement = problem()
    candidates = invalid_assignments(statement, {"choices": (3.0, 3.0)})
    violations = [statement.evaluate(case).violations for case in candidates]
    assert any("capacity" in items for items in violations)
    assert any("choices:lower" in items for items in violations)
    assert all(not statement.evaluate(case).feasible for case in candidates)


def test_worker_checks_reject_a_mechanism_missing_domain_validation(artifact, verification):
    from components.library import standard_registry
    from simulation_core.mechanism import Mechanism
    from simulation_core.types import ActionSpace, FrozenModel, Outcome, TransitionResult

    statement = artifact.manifest.request.problem

    class Payload(FrozenModel):
        x: float

    class DomainMechanism(Mechanism):
        enforce = False

        def validate_config(self, config):
            pass

        def validate_state(self, config, state):
            pass

        def validate_actions(self, config, state, actions):
            x = actions[0].payload["x"]
            if self.enforce and not statement.evaluate({"x": x}).feasible:
                raise ValueError("Declared variable domain violated")

        def evaluate(self, config, state, actions):
            return Outcome(payoffs={"worker": -((actions[0].payload["x"] - 3.0) ** 2)})

        def transition(self, config, state, actions):
            return TransitionResult(
                public=state.public, outcome=self.evaluate(config, state, actions)
            )

    registry = standard_registry()
    registry.mechanisms["domain_test"] = DomainMechanism
    registry.action_schemas["domain.x"] = Payload
    config = artifact.manifest.simulation
    actor = config.world.actors[0].model_copy(
        update={"action_space": ActionSpace(schemas={"submit": "domain.x"})}
    )
    config = config.model_copy(
        update={
            "benchmark": None,
            "mechanism_id": "domain_test",
            "world": config.world.model_copy(update={"actors": (actor,)}),
        }
    )
    artifact = artifact.model_copy(
        update={
            "manifest": artifact.manifest.model_copy(update={"simulation": config}),
            "benchmark": None,
        }
    )
    spec = verification.model_copy(
        update={
            "action_behavior": "reject_infeasible",
            "reference_cases": (
                ReferenceCase(
                    id="primary", assignments={"x": 1.0}, feasible=True, objectives={"loss": 4.0}
                ),
                ReferenceCase(
                    id="boundary", assignments={"x": 0.0}, feasible=True, objectives={"loss": 9.0}
                ),
            ),
        }
    )
    findings = standard_checks(artifact, registry, spec)
    assert findings[0].status == "failed"
    assert "accepted an action" in findings[0].evidence
    DomainMechanism.enforce = True
    assert standard_checks(artifact, registry, spec)[0].status == "verified"


def test_tool_route_has_no_simulation_and_cannot_override_explicit_intent(plan, tmp_path):
    component = plan.bundle.components[0].model_copy(
        update={
            "kind": "utility",
            "parent_interface": "typing.Callable",
            "symbol": "experiment_extension.payload:compute",
        }
    )
    tool = CodingPlan(
        kind="tool",
        summary="Direct function",
        bundle=plan.bundle.model_copy(update={"components": (component,), "notebook": None}),
        tool=ToolInvocation(
            entrypoint="experiment_extension.payload:compute", arguments={"value": 2}
        ),
        tests=plan.tests,
    )
    assert tool.simulation is None
    request = ExperimentRequest(hypothesis="Compute a function", execution_kind="tool")
    assert not review_plan(PROJECT, request, "fresh", tool)
    assert review_plan(
        PROJECT, request.model_copy(update={"execution_kind": "agent_simulation"}), "fresh", tool
    )
    from agent_tools.contracts import Implementation, SourceFile

    job = materialize(
        tmp_path / "v1",
        request,
        tool,
        Implementation(
            summary="Synthetic never imported",
            files=(SourceFile(path="experiment_extension/__init__.py", content=""),),
        ),
        1,
    )
    assert isinstance(job, ToolJobManifest)
    with pytest.raises(ValidationError):
        CodingPlan(
            kind="tool",
            summary="Wrong",
            bundle=tool.bundle,
            simulation=plan.simulation,
            tool=tool.tool,
            tests=tool.tests,
        )


def test_failed_diagnostic_can_be_exported_without_becoming_an_approved_result(artifact, tmp_path):
    diagnostic = DiagnosticArtifact(result=artifact)
    response = WorkerResponse(bundle_digest="synthetic", checks=(), diagnostic=diagnostic)
    assert not response.passed and response.result is None
    export_diagnostic(diagnostic, tmp_path / "unapproved")
    assert (
        json.loads((tmp_path / "unapproved/UNAPPROVED.json").read_text())["status"] == "unapproved"
    )
    assert (tmp_path / "unapproved/result.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.skipif(
    not Path("/.dockerenv").exists() or os.geteuid() != 10001,
    reason="Direct extension execution stays inside worker",
)
def test_direct_tool_executes_inside_worker_without_runtime(monkeypatch):
    from extension_worker.tools import execute_tool

    module = ModuleType("experiment_extension.synthetic")
    module.compute = lambda left, right: left + right
    monkeypatch.setitem(sys.modules, module.__name__, module)
    job = ToolJobManifest(
        request=ExperimentRequest(hypothesis="Trusted test fixture"),
        tool=ToolInvocation(
            entrypoint="experiment_extension.synthetic:compute", arguments={"left": 2, "right": 3}
        ),
    )
    assert execute_tool(job).output == 5
