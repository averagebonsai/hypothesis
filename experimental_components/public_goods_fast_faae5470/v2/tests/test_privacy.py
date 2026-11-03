"""Privacy and observation boundaries for the public-goods configuration.

Public round feedback (rules, balances, history) is visible to all; simultaneous
uncommitted choices and other actors' private memory are never revealed; only the
mechanism changes saved funds while policies may update their own memory.
"""

import json

import pytest
from experiment_extension.mechanism import (
    ContributionPayload,
    PublicGoodsWithdrawalMechanism,
)

from agent_tools.fixtures import fixture_config, fixture_state
from components.protocols.simultaneous import SimultaneousProtocol
from simulation_core.observation import observe, permissions_for
from simulation_core.types import Action, Decision, SimulationConfig


def _behavior(aid):
    return {
        "actor_id": aid,
        "objective": "Maximize your own final saved balance.",
        "behavioral_instructions": "No assigned social preference or prescribed contribution strategy. Form your own beliefs from permitted observations.",
        "background": "",
    }


SHARED_INSTRUCTIONS = "Rules for the six-round public-goods game with withdrawal after round 3."

REQUIRED_FIELDS = [
    "rounds",
    "endowed_rounds",
    "endowment",
    "multiplier",
    "participant_count",
    "saved_balances",
    "history",
]


def make_simulation_dict():
    actors = []
    for aid in ("p1", "p2", "p3"):
        actors.append(
            {
                "id": aid,
                "kind": "participant",
                "action_space": {
                    "schemas": {
                        "contribute": "experimental.public_goods_fast_faae5470.contribution"
                    }
                },
                "policy_id": "llm.v1",
                "policy_parameters": {
                    "model": "muse-spark-1.3-contributor",
                    "instructions": SHARED_INSTRUCTIONS,
                    "behavior": _behavior(aid),
                    "required_fields": REQUIRED_FIELDS,
                    "max_attempts": 2,
                    "max_calls": 12,
                },
            }
        )
    permissions = {
        aid: {
            "public_fields": REQUIRED_FIELDS,
            "private_fields": [],
            "readable_memory": True,
            "writable_private_fields": [],
            "writable_memory": True,
        }
        for aid in ("p1", "p2", "p3")
    }
    return {
        "schema_version": "simulation.config.v1",
        "world": {
            "actors": actors,
            "parameters": {
                "participant_count": 3,
                "rounds": 6,
                "endowed_rounds": 3,
                "endowment": 20.0,
                "multiplier": 2.0,
            },
            "initial_public_state": {
                "rounds": 6,
                "endowed_rounds": 3,
                "endowment": 20.0,
                "multiplier": 2.0,
                "participant_count": 3,
                "saved_balances": {"p1": 0.0, "p2": 0.0, "p3": 0.0},
                "history": [],
            },
            "initial_private_state": {
                aid: {"facts": {}, "memory": {}} for aid in ("p1", "p2", "p3")
            },
        },
        "mechanism_id": "experimental.public_goods_fast_faae5470.mechanism",
        "protocol_id": "simultaneous.v1",
        "protocol_parameters": {"rounds": 6},
        "permissions": permissions,
        "max_steps": 6,
        "assumptions": [
            {
                "path": "/world/parameters/rounds",
                "value": 6,
                "source": "user",
                "rationale": "The game lasts six simultaneous rounds.",
            },
            {
                "path": "/world/parameters/endowed_rounds",
                "value": 3,
                "source": "user",
                "rationale": "Fresh endowments stop after round 3.",
            },
            {
                "path": "/mechanism_id",
                "value": "experimental.public_goods_fast_faae5470.mechanism",
                "source": "model",
                "rationale": "Custom withdrawal and budget rules settle payoffs.",
            },
        ],
    }


@pytest.fixture()
def config():
    return fixture_config(make_simulation_dict())


def test_config_round_trips_through_json_boundary(config):
    clone = SimulationConfig.from_json_values(json.loads(config.model_dump_json()))
    assert clone == config
    assert PublicGoodsWithdrawalMechanism().validate_config(clone.world) is None


def test_public_feedback_visible_to_all(config):
    protocol = SimultaneousProtocol(config.protocol_parameters)
    state = fixture_state(config, protocol)
    # Contributions (10, 20, 0): pool 20 each, payoffs 30/20/40, same closings.
    batch = [
        Action(actor_id="p1", kind="contribute", payload={"contribution": 10.0}),
        Action(actor_id="p2", kind="contribute", payload={"contribution": 20.0}),
        Action(actor_id="p3", kind="contribute", payload={"contribution": 0.0}),
    ]
    transition = PublicGoodsWithdrawalMechanism().transition(config.world, state, batch)
    assert transition.outcome.payoffs == {"p1": 30.0, "p2": 20.0, "p3": 40.0}
    public = dict(transition.public)
    state = state.model_copy(update={"public": public, "tick": 1})
    actors = {actor.id: actor for actor in config.world.actors}
    for aid in ("p1", "p2", "p3"):
        obs = observe(actors[aid], state, permissions_for(config, aid, state.phase))
        assert obs.visible["history"] == public["history"]
        assert obs.visible["saved_balances"] == public["saved_balances"]
        assert obs.visible["endowed_rounds"] == 3
        assert obs.allowed_action_kinds == ("contribute",)


def test_private_memory_isolated_between_actors(config):
    protocol = SimultaneousProtocol(config.protocol_parameters)
    state = fixture_state(config, protocol)
    private = {aid: item.model_copy(deep=True) for aid, item in state.private.items()}
    private["p2"] = private["p2"].model_copy(update={"memory": {"note": "p2 secret plan"}})
    state = state.model_copy(update={"private": private})
    actors = {actor.id: actor for actor in config.world.actors}
    obs1 = observe(actors["p1"], state, permissions_for(config, "p1", state.phase))
    obs2 = observe(actors["p2"], state, permissions_for(config, "p2", state.phase))
    assert obs1.private.memory == {}
    assert obs2.private.memory == {"note": "p2 secret plan"}
    assert "p2 secret plan" not in json.dumps(obs1.model_dump(mode="json"))
    legal = [
        Action(actor_id=aid, kind="contribute", payload={"contribution": 1.0})
        for aid in ("p1", "p2", "p3")
    ]
    assert PublicGoodsWithdrawalMechanism().validate_actions(config.world, state, legal) is None


def test_policy_cannot_write_budgets_but_may_write_memory(config):
    for aid in ("p1", "p2", "p3"):
        permissions = permissions_for(config, aid, "act")
        assert list(permissions.writable_private_fields) == []
        assert permissions.writable_memory is True
        decision = Decision.model_validate(
            {
                "action": {
                    "actor_id": aid,
                    "kind": "contribute",
                    "payload": {"contribution": 1.0},
                },
                "rationale": "test rationale",
                "private_updates": {"saved_balances": {aid: 999.0}},
            }
        )
        assert set(decision.private_updates) - set(permissions.writable_private_fields)
    contract = PublicGoodsWithdrawalMechanism().required_action_schemas(config.world)
    assert set(contract) == {"p1", "p2", "p3"}


def test_required_observation_fields_covered_by_permissions(config):
    for actor in config.world.actors:
        required = set(actor.policy_parameters["required_fields"])
        allowed = set(permissions_for(config, actor.id, "act").public_fields)
        assert required <= allowed
    assert set(ContributionPayload.model_json_schema()["required"]) == {"contribution"}


def test_observations_reveal_only_committed_rounds(config):
    protocol = SimultaneousProtocol(config.protocol_parameters)
    state = fixture_state(config, protocol)
    actors = {actor.id: actor for actor in config.world.actors}
    obs = observe(actors["p1"], state, permissions_for(config, "p1", state.phase))
    assert obs.visible["history"] == []
    assert "pending" not in json.dumps(obs.model_dump(mode="json")).lower()
    assert PublicGoodsWithdrawalMechanism().validate_config(config.world) is None
