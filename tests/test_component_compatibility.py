"""Composition errors must be detected without paying for actor decisions."""

import pytest

from components.library import standard_registry
from components.mechanisms.stackelberg import QuantityPayload
from examples.stackelberg import build_experiment, fake_response, illustrative_inputs
from simulation_core.execution import JobRunner, LocalBackend
from simulation_core.model_gateway import FakeGateway
from simulation_core.registry import ComponentCompatibilityError
from simulation_core.runtime import SimulationRuntime
from simulation_core.types import ActionSpace, BenchmarkSpec, ObservationPermissions


def fixture():
    gateway = FakeGateway(fake_response)
    request, config = build_experiment(illustrative_inputs())
    return (
        request,
        config.model_copy(update={"assumptions": ()}),
        standard_registry(gateway),
        gateway,
    )


@pytest.mark.parametrize(
    "view,solver,message",
    [
        ("homogeneous_bertrand.v1", "textbook_bertrand.v1", "homogeneous Bertrand"),
        ("normal_form.v1", "pure_nash.v1", "payoff-matrix"),
        ("stackelberg.v1", "pure_nash.v1", "FiniteGameView"),
        ("stackelberg.v1", "numerical_nash.v1", "DifferentiableScalarGameView"),
    ],
)
def test_bad_benchmark_pairing_fails_before_gateway_calls(tmp_path, view, solver, message):
    request, config, registry, gateway = fixture()
    config = config.model_copy(
        update={"benchmark": BenchmarkSpec(game_view_id=view, solver_id=solver)}
    )
    with pytest.raises(ComponentCompatibilityError, match=message):
        JobRunner(LocalBackend(registry), tmp_path).run(request, config)
    assert gateway.requests == []
    assert list(tmp_path.iterdir()) == []


def test_wrong_protocol_rejected_even_when_runtime_called_directly():
    _, config, registry, gateway = fixture()
    config = config.model_copy(
        update={
            "protocol_id": "simultaneous.v1",
            "protocol_parameters": {"rounds": 1},
            "phase_permissions": {},
        }
    )
    with pytest.raises(ComponentCompatibilityError, match="leader stage"):
        SimulationRuntime(registry).run(config)
    assert gateway.requests == []


def test_wrong_payload_contract_rejected_before_policy_execution():
    _, config, registry, gateway = fixture()
    actors = tuple(
        actor.model_copy(update={"action_space": ActionSpace(schemas={"set_quantity": "price.v1"})})
        for actor in config.world.actors
    )
    config = config.model_copy(update={"world": config.world.model_copy(update={"actors": actors})})
    with pytest.raises(ComponentCompatibilityError, match="QuantityPayload"):
        SimulationRuntime(registry).run(config)
    assert gateway.requests == []


def test_equivalent_schema_can_have_a_different_model_name():
    class CustomQuantity(QuantityPayload):
        pass

    _, config, registry, gateway = fixture()
    registry.action_schemas["quantity.v1"] = CustomQuantity
    assert SimulationRuntime(registry).run(config).status == "completed"
    assert len(gateway.requests) == 2


def test_later_phase_permission_mismatch_is_detected_before_first_action():
    _, config, registry, gateway = fixture()
    overrides = {
        **config.phase_permissions,
        "follower_response": {"Follower": ObservationPermissions(public_fields=("market",))},
    }
    config = config.model_copy(update={"phase_permissions": overrides})
    with pytest.raises(ComponentCompatibilityError, match="Follower.*follower_response"):
        SimulationRuntime(registry).run(config)
    assert gateway.requests == []


def test_discovery_exposes_solver_capability_requirements():
    _, config, registry, gateway = fixture()
    inventory = registry.describe()
    assert inventory["solver_requirements"]["numerical_nash.v1"] == "DifferentiableScalarGameView"
    registry.validate_config(config)
    assert gateway.requests == []


def test_joint_mechanism_cannot_be_scheduled_as_separate_actor_decisions():
    from components.protocols.sequential import DecisionPhase, SequentialParameters
    from examples.payoff_matrix import build_experiment as matrix_experiment

    config, registry = matrix_experiment()
    phases = SequentialParameters(
        phases=tuple(
            DecisionPhase(name=actor.id, actor_ids=(actor.id,)) for actor in config.world.actors
        )
    )
    config = config.model_copy(
        update={
            "protocol_id": "sequential.v1",
            "protocol_parameters": phases.model_dump(mode="json"),
            "assumptions": (),
        }
    )
    with pytest.raises(ComponentCompatibilityError, match="joint action batch"):
        registry.validate_config(config)


def test_extra_policy_action_kind_is_incompatible_with_a_closed_mechanism():
    _, config, registry, gateway = fixture()
    actors = tuple(
        actor.model_copy(
            update={
                "action_space": ActionSpace(
                    schemas={"set_quantity": "quantity.v1", "send_message": "number.v1"}
                )
            }
        )
        for actor in config.world.actors
    )
    config = config.model_copy(update={"world": config.world.model_copy(update={"actors": actors})})
    with pytest.raises(ComponentCompatibilityError, match="action kinds"):
        SimulationRuntime(registry).run(config)
    assert gateway.requests == []
