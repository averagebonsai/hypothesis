import json

import pytest
from pydantic import ValidationError

from components.mechanisms.normal_form import PayoffMatrixMechanism
from components.policies.scripted import ScriptedPolicy
from components.protocols.simultaneous import SimultaneousProtocol
from examples.payoff_matrix import build_experiment as original_build_experiment
from examples.payoff_matrix import run_experiment
from simulation_core.logging import replay
from simulation_core.runtime import SimulationRuntime
from simulation_core.types import (
    Action,
    Decision,
    Event,
    ObservationPermissions,
    Outcome,
    PrivateState,
    RunResult,
    TransitionResult,
    WorldConfig,
    WorldState,
)


def build_experiment(*args, **kwargs):
    config, registry = original_build_experiment(*args, **kwargs)
    # Adversarial fixture changes test execution boundaries, not provenance consistency.
    return config.model_copy(update={"assumptions": ()}), registry


def test_known_profile_and_replay():
    result = run_experiment()
    assert result.status == "completed"
    assert result.outcomes[0].payoffs == {"A": 0.0, "B": 5.0}
    assert result.final_state.tick == 1
    assert replay(result.events)[-1] == result.final_state
    assert result.final_state.private["A"].memory == {"last_move": "cooperate"}
    restored = RunResult.model_validate_json(result.model_dump_json())
    assert replay(restored.events)[-1] == result.final_state


def test_repeated_game_determinism_limit_and_run_isolation():
    first = run_experiment(rounds=3)
    assert first == run_experiment(rounds=3)
    assert len(first.final_state.public["history"]) == 3
    assert run_experiment(rounds=3, max_steps=2).status == "step_limit"
    first.final_state.public["history"].clear()
    assert len(run_experiment().final_state.public["history"]) == 1


@pytest.mark.parametrize(
    "action",
    [
        Action(actor_id="B", kind="choose_move", payload={"move": "cooperate"}),
        Action(actor_id="A", kind="exit", payload={}),
        Action(actor_id="A", kind="choose_move", payload={"move": "bad"}),
        Action(actor_id="A", kind="choose_move", payload={"move": "cooperate", "extra": True}),
    ],
)
def test_bad_actions_never_reach_transition(action):
    config, registry = build_experiment()

    class BadPolicy(ScriptedPolicy):
        def choose_action(self, observation):
            return Decision(action=action)

    class NoTransition(PayoffMatrixMechanism):
        def validate_config(self, config):
            pass

        def transition(self, *args):
            pytest.fail("Invalid action reached transition")

    registry.policies["scripted.v1"] = lambda params: BadPolicy(params)
    registry.mechanisms["normal_form.v1"] = NoTransition
    with pytest.raises((ValueError, ValidationError)):
        SimulationRuntime(registry).run(config)


def test_observations_are_private_and_simultaneous_in_either_order():
    observations = []

    class WatchingPolicy(ScriptedPolicy):
        def choose_action(self, observation):
            observations.append(observation.model_copy(deep=True))
            observation.visible["history"].append({"leak": True})
            observation.private.memory["tampered"] = True
            return super().choose_action(observation)

    config, registry = build_experiment(rounds=2)
    world = config.world.model_copy(
        update={
            "initial_private_state": {
                "A": PrivateState(facts={"secret": "A-only"}, memory={"own": "A"}),
                "B": PrivateState(facts={"secret": "B-only"}, memory={"own": "B"}),
            }
        }
    )
    config = config.model_copy(update={"world": world})
    config = config.model_copy(
        update={
            "permissions": {
                aid: ObservationPermissions(
                    public_fields=("history", "payoffs"), private_fields=("secret",)
                )
                for aid in ("A", "B")
            }
        }
    )
    registry.policies = {key: WatchingPolicy for key in registry.policies}
    result = SimulationRuntime(registry).run(config)
    assert observations[0].visible == observations[1].visible == {"history": []}
    for observation in observations:
        assert observation.private.facts == {"secret": observation.actor_id + "-only"}
        assert "tampered" not in observation.private.memory
    assert len(result.final_state.public["history"]) == 2
    original = observations[:2]
    observations.clear()

    class ReverseProtocol(SimultaneousProtocol):
        def active_actor_ids(self, config, state):
            return tuple(reversed(super().active_actor_ids(config, state)))

    registry.protocols["simultaneous.v1"] = ReverseProtocol
    reversed_result = SimulationRuntime(registry).run(config)
    assert result.final_state == reversed_result.final_state
    assert {o.actor_id: o for o in observations[:2]} == {o.actor_id: o for o in original}
    assert config.world.initial_public_state == {"history": []}


def test_observation_leaks_and_missing_requirements_rejected():
    config, registry = build_experiment()

    class NeedyPolicy(ScriptedPolicy):
        def required_observation_fields(self):
            return frozenset({"secret"})

    registry.policies["scripted.v1"] = NeedyPolicy
    with pytest.raises(ValueError, match="unavailable"):
        SimulationRuntime(registry).run(config)


def test_configuration_and_finite_values():
    config, registry = build_experiment()
    with pytest.raises(ValidationError):
        WorldConfig(actors=(config.world.actors[0], config.world.actors[0]))
    with pytest.raises(ValidationError):
        WorldConfig(actors=config.world.actors, initial_private_state={"unknown": PrivateState()})
    with pytest.raises(ValidationError):
        Outcome(payoffs={"A": float("nan")})
    with pytest.raises(ValidationError):
        PrivateState(memory={"nested": [float("inf")]})
    with pytest.raises(ValidationError):
        PrivateState(memory={"python_object": object()})
    registry.action_schemas.clear()
    with pytest.raises(ValueError, match="schema"):
        SimulationRuntime(registry).run(config)


def test_invalid_transition_and_isolated_mechanism_inputs():
    config, registry = build_experiment()
    original = registry.mechanisms["normal_form.v1"]()

    class BadMechanism(PayoffMatrixMechanism):
        def validate_state(self, config, state):
            original.validate_state(config, state)

        def validate_config(self, config):
            original.validate_config(config)

        def transition(self, config, state, actions):
            state.public["history"].append("bad")
            return TransitionResult(public=state.public, outcome=Outcome(payoffs={"unknown": 1.0}))

    registry.mechanisms["normal_form.v1"] = BadMechanism
    with pytest.raises(ValueError, match="Unknown actor"):
        SimulationRuntime(registry).run(config)
    assert config.world.initial_public_state == {"history": []}
    registry.mechanisms["normal_form.v1"] = lambda: original
    result = SimulationRuntime(registry).run(config)
    assert result.events[0].state.public == {"history": []}


def test_evaluate_is_pure_and_batch_must_be_complete():
    config, registry = build_experiment()
    state = WorldState(tick=0, phase="choose", public={"history": []})
    actions = (
        Action(actor_id="A", kind="choose_move", payload={"move": "cooperate"}),
        Action(actor_id="B", kind="choose_move", payload={"move": "defect"}),
    )
    before = state.model_dump_json()
    mechanism = registry.mechanisms["normal_form.v1"]()
    assert mechanism.evaluate(config.world, state, actions).payoffs == {"A": 0.0, "B": 5.0}
    assert state.model_dump_json() == before
    protocol = registry.protocols["simultaneous.v1"](config.protocol_parameters)
    for batch in (actions[:1], (actions[0], actions[0])):
        with pytest.raises(ValueError):
            protocol.validate_action_batch(config.world, state, batch)


def test_replay_rejects_broken_sequence():
    result = run_experiment()
    with pytest.raises(ValueError):
        replay(result.events[1:])
    with pytest.raises(ValueError):
        replay(())
    serialized = json.loads(result.model_dump_json())
    serialized["events"][1]["sequence"] = 8
    with pytest.raises(ValueError):
        replay(tuple(Event.model_validate_json(json.dumps(e)) for e in serialized["events"]))
