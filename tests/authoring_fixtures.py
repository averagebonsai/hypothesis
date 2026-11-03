"""Offline checks: synthetic artifacts only, no coding API or experimental execution."""

from pathlib import Path

import pytest

from agent_tools.authoring import CodingPlan, SourceFile
from agent_tools.specs import (
    BundleManifest,
    ObjectiveBinding,
    VariableBinding,
    VerificationSpec,
)
from simulation_core.benchmark import BenchmarkReport
from simulation_core.execution import JobManifest, JobResult
from simulation_core.problems import (
    Constant,
    ObjectiveSpec,
    Operation,
    ProblemActor,
    ProblemStatement,
    Reference,
    VariableSpec,
)
from simulation_core.request import ExperimentRequest
from simulation_core.solver import Equilibrium, SolveResult
from simulation_core.types import (
    Action,
    ActionSpace,
    Actor,
    BenchmarkSpec,
    Event,
    Outcome,
    RunResult,
    SimulationConfig,
    WorldConfig,
    WorldState,
)

PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture
def plan():
    manifest = BundleManifest.from_json_values(
        {
            "experiment_id": "fresh",
            "version": "v1",
            "gap_analysis": {
                "objective": "Synthetic payload",
                "decisions": [
                    {
                        "requirement": {
                            "id": "payload",
                            "description": "New payload",
                            "action_shape": "scalar",
                        },
                        "disposition": "EXTEND",
                        "reason": "Synthetic schema extension",
                    }
                ],
            },
            "components": [
                {
                    "id": "experimental.fresh.payload",
                    "kind": "action_schema",
                    "purpose": "Payload",
                    "gap_id": "payload",
                    "parent_interface": "pydantic.BaseModel",
                    "symbol": "experiment_extension.payload:Payload",
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                    "acceptance_tests": [
                        {
                            "name": "test_payload",
                            "category": "interface",
                            "expected": "Component invoked",
                            "reference": "Synthetic contract",
                        }
                    ],
                }
            ],
            "notebook": {
                "generator": "experiment_extension.reporting:write_notebook",
                "report_version": "explanatory.v1",
                "preview_generator": "experiment_extension.reporting:preview",
            },
        }
    )
    config = SimulationConfig.model_validate_json(
        (PROJECT / "src/examples/configs/measurements.json").read_text()
    )
    return CodingPlan(
        summary="Synthetic pre-freeze test",
        bundle=manifest,
        simulation=config,
        tests=(
            SourceFile(
                path="tests/test_payload.py",
                content="from experiment_extension.payload import Payload\n\n\ndef test_payload():\n    assert Payload(value=2).value == 2\n",
            ),
        ),
    )


@pytest.fixture
def artifact():
    # Hand-constructed data, not a simulation run or a previous experiment result.
    problem = ProblemStatement(
        description="Scalar squared loss",
        evaluation="deterministic",
        actors=(ProblemActor(id="worker"),),
        variables=(
            VariableSpec(name="x", actor_id="worker", shape="scalar", lower=0.0, upper=5.0),
        ),
        objectives=(
            ObjectiveSpec(
                name="loss",
                actor_id="worker",
                sense="minimize",
                expression=Operation(
                    operator="square",
                    arguments=(
                        Operation(
                            operator="subtract",
                            arguments=(Reference(name="x"), Constant(value=3.0)),
                        ),
                    ),
                ),
            ),
        ),
    )
    config = SimulationConfig(
        world=WorldConfig(
            actors=(
                Actor(
                    id="worker",
                    kind="synthetic",
                    action_space=ActionSpace(schemas={"submit": "number.v1"}),
                    policy_id="scripted.v1",
                    policy_parameters={"kind": "submit", "payload": {"x": 1.0}},
                ),
            )
        ),
        mechanism_id="recording.v1",
        protocol_id="simultaneous.v1",
        protocol_parameters={"rounds": 1},
        benchmark=BenchmarkSpec(solver_id="synthetic", game_view_id="synthetic"),
    )
    action = Action(actor_id="worker", kind="submit", payload={"x": 1.0})
    outcome = Outcome(payoffs={"worker": -4.0})
    state = WorldState(tick=1, phase="finished")
    result = RunResult(
        status="completed",
        final_state=state,
        outcomes=(outcome,),
        events=(
            Event(sequence=0, kind="committed", state=state, actions=(action,), outcome=outcome),
        ),
        assumptions=(),
        component_ids=(),
    )
    benchmark = BenchmarkReport(
        config_sha256="synthetic",
        result=SolveResult(
            status="solved",
            equilibria=(
                Equilibrium(
                    actions=(action.model_copy(update={"payload": {"x": 3.0}}),),
                    outcome=Outcome(payoffs={"worker": 0.0}),
                    regrets={"worker": 0.0},
                ),
            ),
        ),
    )
    return JobResult(
        manifest=JobManifest(
            request=ExperimentRequest(hypothesis="Synthetic scalar problem", problem=problem),
            simulation=config,
        ),
        result=result,
        benchmark=benchmark,
    )


@pytest.fixture
def verification():
    return VerificationSpec(
        variables=(VariableBinding(variable="x", actor_id="worker", payload_field="x"),),
        objectives=(ObjectiveBinding(objective="loss", source="payoff", key="worker", scale=-1),),
        independent_reference="single_objective_slsqp",
    )
