from importlib.resources import files
from itertools import product

import pytest
from pydantic import ValidationError

from components.library import standard_registry
from components.mechanisms.normal_form import PayoffMatrixMechanism
from components.mechanisms.recording import RecordingMechanism
from components.policies.scripted import ScriptedPolicy
from components.protocols.simultaneous import SimultaneousProtocol
from examples.measurements import run_experiment as run_measurements
from examples.payoff_matrix import build_experiment as original_build_experiment
from simulation_core.logging import replay
from simulation_core.mechanism import Mechanism
from simulation_core.observation import observe
from simulation_core.policy import Policy
from simulation_core.protocol import ProtocolRules
from simulation_core.runtime import SimulationRuntime
from simulation_core.types import (
    ActionSpace,
    Actor,
    ObservationPermissions,
    Outcome,
    PrivateState,
    SimulationConfig,
    WorldConfig,
)


def build_experiment(*args, **kwargs):
    config, registry = original_build_experiment(*args, **kwargs)
    # Adversarial fixture changes test execution boundaries, not provenance consistency.
    return config.model_copy(update={"assumptions": ()}), registry


def test_explicit_parent_contracts_and_discovery():
    assert issubclass(ScriptedPolicy, Policy)
    assert issubclass(PayoffMatrixMechanism, Mechanism)
    assert issubclass(RecordingMechanism, Mechanism)
    assert issubclass(SimultaneousProtocol, ProtocolRules)
    for interface in (Policy, Mechanism, ProtocolRules):
        with pytest.raises(TypeError):
            interface()
    inventory = standard_registry().describe()
    assert "scripted.v1" in inventory["policies"]
    assert "rounds" in inventory["parameter_schemas"]["simultaneous.v1"]["properties"]


def test_unrelated_numeric_experiment_without_payoffs():
    result = run_measurements()
    assert result.status == "completed"
    assert result.final_state.tick == 2
    assert len(result.final_state.public["readings"]) == 2
    assert all(outcome.payoffs == {} for outcome in result.outcomes)
    assert result.outcomes[-1].metrics == {"received": 3}
    assert replay(result.events)[-1] == result.final_state
    assert result.final_state.private["north"].facts["calibrated"] is True
    assert result.final_state.private["south"].facts["calibration_secret"] == "south"
    assert result == run_measurements()


def test_asymmetric_three_player_matrix_has_no_experiment_labels():
    choices = {"first": ["red", "blue", "green"], "second": ["wait"], "third": ["up", "down"]}
    config = SimulationConfig(
        world=WorldConfig(
            actors=tuple(
                Actor(
                    id=aid,
                    kind="player",
                    policy_id="scripted.v1",
                    policy_parameters={"kind": "select", "payload": {"move": moves[0]}},
                    action_space=ActionSpace(schemas={"select": "move.v1"}),
                )
                for aid, moves in choices.items()
            ),
            parameters={
                "choices": choices,
                "cells": [
                    {
                        "moves": dict(zip(choices, profile)),
                        "payoffs": {aid: float(i) for i, aid in enumerate(choices)},
                    }
                    for profile in product(*choices.values())
                ],
                "action_kind": "select",
                "history_field": "profiles",
                "payoffs_field": "utilities",
            },
            initial_public_state={"profiles": []},
        ),
        mechanism_id="normal_form.v1",
        protocol_id="simultaneous.v1",
        protocol_parameters={"rounds": 1},
    )
    result = SimulationRuntime(standard_registry()).run(config)
    assert result.outcomes[0].payoffs == {"first": 0.0, "second": 1.0, "third": 2.0}
    assert result.final_state.public["profiles"] == [
        {"first": "red", "second": "wait", "third": "up"}
    ]
    params = dict(config.world.parameters)
    params["cells"] = params["cells"][:-1]
    with pytest.raises(ValueError, match="cover"):
        SimulationRuntime(standard_registry()).run(
            config.model_copy(
                update={"world": config.world.model_copy(update={"parameters": params})}
            )
        )


def measurement_config():
    return SimulationConfig.model_validate_json(
        files("examples").joinpath("configs/measurements.json").read_text()
    ).model_copy(update={"assumptions": ()})


def test_permissions_are_runtime_owned_not_protocol_projections():
    config = measurement_config()
    seen = []

    class WatchingPolicy(ScriptedPolicy):
        def choose_action(self, observation):
            seen.append(observation.model_copy(deep=True))
            assert "internal_note" not in observation.visible
            assert observation.private.facts["calibration_secret"] == observation.actor_id
            observation.private.facts["calibration_secret"] = "tampered"
            return super().choose_action(observation)

    class UntrustedObservationMethod(SimultaneousProtocol):
        def observe(self, *args):
            pytest.fail("Runtime must never ask scheduling components for observations")

    registry = standard_registry()
    registry.policies["scripted.v1"] = WatchingPolicy
    registry.protocols["simultaneous.v1"] = UntrustedObservationMethod
    result = SimulationRuntime(registry).run(config)
    assert len(seen) == 6
    assert all(
        v.facts["calibration_secret"] == aid for aid, v in result.final_state.private.items()
    )
    state = result.final_state
    actor = config.world.actors[0]
    denied = observe(actor, state, ObservationPermissions(readable_memory=False))
    assert denied.visible == {} and denied.private.facts == {} and denied.private.memory == {}


@pytest.mark.parametrize("change", ["private", "memory"])
def test_write_permissions_enforced_before_transition(change):
    config = measurement_config()
    permissions = dict(config.permissions)
    permissions["north"] = ObservationPermissions(
        public_fields=("instructions",),
        writable_memory=change != "memory",
        writable_private_fields=() if change == "private" else ("calibrated",),
    )
    with pytest.raises(ValueError, match="Unauthorized"):
        SimulationRuntime(standard_registry()).run(
            config.model_copy(update={"permissions": permissions})
        )


def test_nonactive_actor_is_not_asked_to_act_and_partial_payoffs_allowed():
    config = measurement_config().model_copy(update={"protocol_parameters": {"rounds": 1}})

    class OneActive(SimultaneousProtocol):
        def active_actor_ids(self, config, state):
            return (config.actors[0].id,)

    registry = standard_registry()
    registry.protocols["simultaneous.v1"] = OneActive
    result = SimulationRuntime(registry).run(config)
    assert len(result.events[-1].actions) == 1
    assert result.final_state.private["south"].facts["calibrated"] is False
    assert result.outcomes[0].metrics == {"received": 1}


def test_fresh_policy_instance_per_actor_and_per_run():
    config, registry = build_experiment()

    class StatefulPolicy(ScriptedPolicy):
        def __init__(self, params):
            super().__init__(params)
            self.calls = 0

        def choose_action(self, observation):
            self.calls += 1
            assert self.calls == 1
            return super().choose_action(observation)

    registry.policies["scripted.v1"] = StatefulPolicy
    runtime = SimulationRuntime(registry)
    assert runtime.run(config) == runtime.run(config)


def test_state_invariants_and_private_transition_validation():
    config, registry = build_experiment()

    class InvalidState(PayoffMatrixMechanism):
        def transition(self, config, state, actions):
            result = super().transition(config, state, actions)
            result.public["history"] = []
            return result

    registry.mechanisms["normal_form.v1"] = InvalidState
    with pytest.raises(ValueError, match="History"):
        SimulationRuntime(registry).run(config)

    class ForeignPrivate(PayoffMatrixMechanism):
        def transition(self, config, state, actions):
            result = super().transition(config, state, actions)
            return result.model_copy(update={"private_updates": {"stranger": PrivateState()}})

    registry.mechanisms["normal_form.v1"] = ForeignPrivate
    with pytest.raises(ValueError, match="Unknown actor"):
        SimulationRuntime(registry).run(config)

    class ConflictingPrivate(PayoffMatrixMechanism):
        def transition(self, config, state, actions):
            result = super().transition(config, state, actions)
            return result.model_copy(update={"private_updates": {"A": PrivateState()}})

    registry.mechanisms["normal_form.v1"] = ConflictingPrivate
    with pytest.raises(ValueError, match="Conflicting"):
        SimulationRuntime(registry).run(config)


def test_partial_payoffs_are_valid_domain_outcomes():
    config = measurement_config()
    registry = standard_registry()

    class PartialPayoff(RecordingMechanism):
        def evaluate(self, config, state, actions):
            return Outcome(payoffs={"north": 1.0}, metrics={"received": len(actions)})

    registry.mechanisms["recording.v1"] = PartialPayoff
    result = SimulationRuntime(registry).run(config)
    assert result.outcomes[-1].payoffs == {"north": 1.0}


def test_config_round_trip_permissions_and_component_parameters():
    config = measurement_config()
    assert SimulationConfig.model_validate_json(config.model_dump_json()) == config
    permissions = {"stranger": ObservationPermissions()}
    with pytest.raises(ValidationError, match="Unknown actor"):
        SimulationConfig.model_validate(
            config.model_copy(update={"permissions": permissions}).model_dump()
        )
    with pytest.raises(ValueError):
        SimulationRuntime(standard_registry()).run(
            config.model_copy(update={"protocol_parameters": {"rounds": 0}})
        )
    with pytest.raises(ValueError):
        SimulationRuntime(standard_registry()).run(
            config.model_copy(update={"protocol_parameters": {"rounds": 1, "typo": True}})
        )
