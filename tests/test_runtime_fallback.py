from collections.abc import Sequence

import pytest

from components.mechanisms.normal_form import PayoffMatrixMechanism
from components.policies.scripted import ScriptedPolicy
from examples.payoff_matrix import build_experiment as base_build_experiment
from simulation_core.registry import ComponentRegistry
from simulation_core.runtime import SimulationRuntime
from simulation_core.types import (
    Action,
    Decision,
    Observation,
    SimulationConfig,
    WorldConfig,
    WorldState,
)


def build_test_experiment(rounds: int = 1) -> tuple[SimulationConfig, ComponentRegistry]:
    config, registry = base_build_experiment(rounds=rounds)
    return config.model_copy(update={"assumptions": ()}), registry


def test_mechanism_rejection_triggers_safe_fallback() -> None:
    config, registry = build_test_experiment(rounds=1)

    class RejectionMechanism(PayoffMatrixMechanism):
        def validate_actions(
            self, world: WorldConfig, state: WorldState, actions: Sequence[Action]
        ) -> None:
            super().validate_actions(world, state, actions)
            for action in actions:
                # Reject actor A choosing "defect" as an illegal move
                if action.actor_id == "A" and action.payload.get("move") == "defect":
                    raise ValueError(f"Action '{action.payload}' exceeds allowable physical constraint")

    registry.mechanisms["normal_form.v1"] = RejectionMechanism

    # Configure actor 'A' to choose 'defect', but configure a safe fallback to 'cooperate'
    actors = []
    for actor in config.world.actors:
        if actor.id == "A":
            # Policy instructs defect, but safe_fallback provides cooperate
            updated = actor.model_copy(
                update={
                    "policy_parameters": {
                        "kind": "choose_move",
                        "payload": {"move": "defect"},
                    },
                    "attributes": {
                        "safe_fallback_actions": {"choose_move": {"move": "cooperate"}}
                    },
                }
            )
            actors.append(updated)
        else:
            actors.append(actor)

    test_config = config.model_copy(
        update={"world": config.world.model_copy(update={"actors": tuple(actors)})}
    )

    result = SimulationRuntime(registry).run(test_config)
    assert result.status == "completed"
    last_event = result.events[-1]
    a_decision = next(d for d in last_event.decisions if d.action.actor_id == "A")
    # Verified fallback was substituted
    assert a_decision.action.payload == {"move": "cooperate"}
    assert a_decision.rationale is not None and "Runtime safe fallback applied" in a_decision.rationale


def test_policy_failure_triggers_safe_fallback() -> None:
    config, registry = build_test_experiment(rounds=1)

    class FailingPolicy(ScriptedPolicy):
        def choose_action(self, observation: Observation) -> Decision:
            raise RuntimeError("Model gateway call failed or timed out")

    registry.policies["scripted.v1"] = FailingPolicy

    actors = []
    for actor in config.world.actors:
        updated = actor.model_copy(
            update={
                "attributes": {
                    "safe_fallback_actions": {"choose_move": {"move": "cooperate"}}
                }
            }
        )
        actors.append(updated)

    test_config = config.model_copy(
        update={"world": config.world.model_copy(update={"actors": tuple(actors)})}
    )

    result = SimulationRuntime(registry).run(test_config)
    assert result.status == "completed"
    last_event = result.events[-1]
    for decision in last_event.decisions:
        assert decision.action.payload == {"move": "cooperate"}
        assert decision.rationale is not None
        assert "Runtime safe fallback applied after policy failure" in decision.rationale


def test_unrepaired_error_raises_when_no_fallback_configured() -> None:
    config, registry = build_test_experiment(rounds=1)

    class RejectionMechanism(PayoffMatrixMechanism):
        def validate_actions(
            self, world: WorldConfig, state: WorldState, actions: Sequence[Action]
        ) -> None:
            super().validate_actions(world, state, actions)
            raise ValueError("Strict domain invariant violated")

    registry.mechanisms["normal_form.v1"] = RejectionMechanism

    with pytest.raises(ValueError, match="Strict domain invariant violated"):
        SimulationRuntime(registry).run(config)
