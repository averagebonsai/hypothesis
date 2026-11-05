"""Decentralized information boundaries, fallbacks and supplied parameters."""

import copy
import json
from pathlib import Path

from experiment_extension.supplychain import (
    LOGISTICS,
    MANUFACTURER,
    SUPPLIER_A,
    SUPPLIER_B,
    SupplyChainMechanism,
)
from support import INITIAL_PUBLIC, LOGISTICS_FACTS, MANUFACTURER_FACTS, PERMISSIONS, SUPPLIER_FACTS

from simulation_core.observation import observe, permissions_for
from simulation_core.types import Actor, PrivateState, SimulationConfig, WorldState

MECH = SupplyChainMechanism()

FALLBACKS = {
    MANUFACTURER: {
        "order": {"order_a": 0, "order_b": 0, "priority": "none"},
        "produce": {"produce": 0},
    },
    SUPPLIER_A: {"offer": {"produce": 0, "offer": 0, "priority_request": False}},
    SUPPLIER_B: {"offer": {"produce": 0, "offer": 0, "priority_request": False}},
    LOGISTICS: {"allocate": {"alloc_a": 0, "alloc_b": 0}},
}


def draft_simulation() -> SimulationConfig:
    data = json.loads(Path("draft.json").read_text())
    return SimulationConfig.from_json_values(data["simulation"])


def state_at(phase, tick, public=None):
    public_state = copy.deepcopy(INITIAL_PUBLIC)
    public_state.update(copy.deepcopy(public or {}))
    facts = {
        MANUFACTURER: dict(MANUFACTURER_FACTS),
        SUPPLIER_A: dict(SUPPLIER_FACTS),
        SUPPLIER_B: dict(SUPPLIER_FACTS),
        LOGISTICS: dict(LOGISTICS_FACTS),
    }
    facts[SUPPLIER_A]["inventory"] = 321
    facts[SUPPLIER_B]["inventory"] = 123
    facts[MANUFACTURER]["comp_a"] = 111
    return WorldState(
        tick=tick,
        phase=phase,
        public=public_state,
        private={aid: PrivateState(facts=f, memory={}) for aid, f in facts.items()},
    )


def actor_lookup(config):
    return {actor.id: actor for actor in config.world.actors}


def test_suppliers_cannot_observe_each_other():
    config = draft_simulation()
    actors = actor_lookup(config)
    actor = Actor.model_validate(
        {
            **actors[SUPPLIER_A].model_dump(),
            "policy_id": "scripted.v1",
            "policy_parameters": {"kind": "offer", "payload": {}},
        }
    )
    state = state_at("d1_supply", 1, {"pending_offers": {"supplier_a": 40, "supplier_b": 30}})
    observation = observe(actor, state, permissions_for(config, SUPPLIER_A, "d1_supply"))
    assert observation.private.facts["inventory"] == 321
    assert "pending_offers" not in observation.visible
    assert "inventory" not in json.dumps(observation.visible)
    # Supplier B's stock is nowhere in A's observation.
    assert "123" not in json.dumps(observation.model_dump())


def test_manufacturer_sees_commitments_but_not_supplier_stock():
    config = draft_simulation()
    actors = actor_lookup(config)
    actor = Actor.model_validate(
        {
            **actors[MANUFACTURER].model_dump(),
            "policy_id": "scripted.v1",
            "policy_parameters": {"kind": "order", "payload": {}},
        }
    )
    state = state_at("d2_order", 4, {"pending_offers": {"supplier_a": 40, "supplier_b": 30}})
    observation = observe(actor, state, permissions_for(config, MANUFACTURER, "d2_order"))
    assert observation.visible["pending_offers"] == {"supplier_a": 40, "supplier_b": 30}
    assert "321" not in json.dumps(observation.model_dump())
    assert "123" not in json.dumps(observation.model_dump())


def test_logistics_sees_no_manufacturer_inventory_or_demand():
    config = draft_simulation()
    actors = actor_lookup(config)
    actor = Actor.model_validate(
        {
            **actors[LOGISTICS].model_dump(),
            "policy_id": "scripted.v1",
            "policy_parameters": {"kind": "allocate", "payload": {}},
        }
    )
    state = state_at("d1_ship", 2)
    observation = observe(actor, state, permissions_for(config, LOGISTICS, "d1_ship"))
    assert "111" not in json.dumps(observation.model_dump())
    assert "80" not in json.dumps(observation.visible)


def test_simultaneous_suppliers_share_no_uncommitted_actions():
    # Both suppliers act on the same precommit state; neither observes the other.
    config = draft_simulation()
    phases = config.protocol_parameters["phases"]
    supply = [phase for phase in phases if phase["name"] == "d1_supply"]
    assert len(supply) == 1 and set(supply[0]["actor_ids"]) == {SUPPLIER_A, SUPPLIER_B}
    for supplier in (SUPPLIER_A, SUPPLIER_B):
        other = SUPPLIER_B if supplier == SUPPLIER_A else SUPPLIER_A
        permissions = PERMISSIONS[supplier]
        assert other not in json.dumps(permissions)
        assert "pending_offers" not in permissions["public_fields"]


def test_safe_fallback_payloads_pass_mechanism_legality():
    config = draft_simulation().world
    cases = [
        (
            "d1_order",
            0,
            (
                {
                    "actor_id": MANUFACTURER,
                    "kind": "order",
                    "payload": FALLBACKS[MANUFACTURER]["order"],
                },
            ),
        ),
        (
            "d1_supply",
            1,
            (
                {
                    "actor_id": SUPPLIER_A,
                    "kind": "offer",
                    "payload": FALLBACKS[SUPPLIER_A]["offer"],
                },
                {
                    "actor_id": SUPPLIER_B,
                    "kind": "offer",
                    "payload": FALLBACKS[SUPPLIER_B]["offer"],
                },
            ),
        ),
        (
            "d1_ship",
            2,
            (
                {
                    "actor_id": LOGISTICS,
                    "kind": "allocate",
                    "payload": FALLBACKS[LOGISTICS]["allocate"],
                },
            ),
        ),
        (
            "d1_make",
            3,
            (
                {
                    "actor_id": MANUFACTURER,
                    "kind": "produce",
                    "payload": FALLBACKS[MANUFACTURER]["produce"],
                },
            ),
        ),
    ]
    from simulation_core.types import Action

    for phase, tick, payloads in cases:
        state = state_at(phase, tick)
        actions = tuple(Action.model_validate(item) for item in payloads)
        assert MECH.validate_actions(config, state, actions) is None


def test_every_supplied_parameter_is_preserved():
    task = json.loads(Path("/inputs/task.json").read_text())
    simulation = draft_simulation().model_dump(mode="json")
    from simulation_core.provenance import resolve_pointer, same_json

    for item in task["request"]["supplied_inputs"]:
        if item["target_path"] is None:
            continue
        assert same_json(resolve_pointer(simulation, item["target_path"]), item["value"]), item[
            "name"
        ]


def test_actor_behaviors_preserved_verbatim():
    task = json.loads(Path("/inputs/task.json").read_text())
    simulation = draft_simulation()
    actors = {actor.id: actor for actor in simulation.world.actors}
    for behavior in task["request"]["actor_behaviors"]:
        assert actors[behavior["actor_id"]].policy_parameters["behavior"] == behavior
