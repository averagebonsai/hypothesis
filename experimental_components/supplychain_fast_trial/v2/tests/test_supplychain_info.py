"""Decentralized information boundaries, fallbacks and supplied parameters.

All expectations are self-contained: the candidate configuration is rebuilt
from experiment_extension.configuration (the same source the draft generator
uses), and request values are copied here as literals, so these tests also run
from the sealed bundle without draft.json or /inputs/task.json.
"""

import copy
import json

from experiment_extension.configuration import (
    ACTOR_BEHAVIORS,
    SAFE_FALLBACKS,
    simulation_dict,
)
from experiment_extension.supplychain import (
    LOGISTICS,
    MANUFACTURER,
    SUPPLIER_A,
    SUPPLIER_B,
    SupplyChainMechanism,
)
from support import INITIAL_PUBLIC, LOGISTICS_FACTS, MANUFACTURER_FACTS, PERMISSIONS, SUPPLIER_FACTS

from simulation_core.observation import observe, permissions_for
from simulation_core.provenance import resolve_pointer, same_json
from simulation_core.types import Action, Actor, PrivateState, SimulationConfig, WorldState

MECH = SupplyChainMechanism()
EXPERIMENT_ID = "supplychain_fast_trial"

# Request values copied from the experiment request as literals.
EXPECTED_SUPPLIED = [
    ("horizon_days", "/world/parameters/horizon_days", 9),
    (
        "capacity_schedule",
        "/world/parameters/capacity_schedule",
        [
            {"start_day": 1, "end_day": 2, "capacity": 200},
            {"start_day": 3, "end_day": 6, "capacity": 80},
            {"start_day": 7, "end_day": 9, "capacity": 200},
        ],
    ),
    (
        "initial_manufacturer_components",
        "/world/parameters/initial_manufacturer_components",
        {"A": 150, "B": 150},
    ),
    (
        "initial_supplier_inventory",
        "/world/parameters/initial_supplier_inventory",
        {"supplier_a": 200, "supplier_b": 200},
    ),
    (
        "supplier_daily_capacity",
        "/world/parameters/supplier_daily_capacity",
        {"supplier_a": 100, "supplier_b": 100},
    ),
    ("manufacturer_daily_capacity", "/world/parameters/manufacturer_daily_capacity", 100),
    ("daily_demand", "/world/parameters/daily_demand", 80),
    ("initial_finished_goods", "/world/parameters/initial_finished_goods", 0),
    ("transit_days", "/world/parameters/transit_days", 1),
    ("finished_selling_price", "/world/parameters/finished_selling_price", 100.0),
    ("component_prices", "/world/parameters/component_prices", {"A": 20.0, "B": 20.0}),
    (
        "supplier_unit_production_cost",
        "/world/parameters/supplier_unit_production_cost",
        {"supplier_a": 12.0, "supplier_b": 12.0},
    ),
    ("assembly_unit_cost", "/world/parameters/assembly_unit_cost", 15.0),
    ("transport_unit_charge", "/world/parameters/transport_unit_charge", 5.0),
    ("transport_unit_operating_cost", "/world/parameters/transport_unit_operating_cost", 3.0),
    (
        "manufacturer_component_holding_unit_cost",
        "/world/parameters/manufacturer_component_holding_unit_cost",
        1.0,
    ),
    ("supplier_holding_unit_cost", "/world/parameters/supplier_holding_unit_cost", 0.5),
    (
        "finished_goods_holding_unit_cost",
        "/world/parameters/finished_goods_holding_unit_cost",
        2.0,
    ),
    ("phase transition budget", "/max_steps", 36),
]

EXPECTED_BEHAVIORS = [
    {
        "actor_id": "manufacturer",
        "objective": (
            "Maximize fulfilled customer demand while minimizing inventory holding and procurement "
            "costs and production disruptions."
        ),
        "behavioral_instructions": (
            "Use only your own inventory, demand, orders, capacity and accounting, plus explicitly "
            "communicated commitments and shipment confirmations. Request orders/priorities in the "
            "ordering phase and production in the later manufacturing phase; no premature use of "
            "in-transit components."
        ),
        "background": "",
    },
    {
        "actor_id": "supplier_a",
        "objective": (
            "Maximize revenue earned on actual dispatched Component A while minimizing production, "
            "holding and unfulfilled-order costs."
        ),
        "behavioral_instructions": (
            "Control only Component A. Use your own inventory/capacity/costs/backlog and received "
            "orders. Do not observe Supplier B's inventory, production decisions or order backlog. "
            "Priorities are requests, not guaranteed allocations."
        ),
        "background": "",
    },
    {
        "actor_id": "supplier_b",
        "objective": (
            "Maximize revenue earned on actual dispatched Component B while minimizing production, "
            "holding and unfulfilled-order costs."
        ),
        "behavioral_instructions": (
            "Control only Component B. Use your own inventory/capacity/costs/backlog and received "
            "orders. Do not observe Supplier A's inventory, production decisions or order backlog. "
            "Priorities are requests, not guaranteed allocations."
        ),
        "background": "",
    },
    {
        "actor_id": "logistics",
        "objective": (
            "Maximize completed deliveries and transport revenue while minimizing unused capacity, "
            "operating costs and unfulfilled shipment requests."
        ),
        "behavioral_instructions": (
            "Use submitted shipment requests/priorities, current transport capacity, your pending "
            "shipments and own costs. Do not observe the manufacturer's inventory or demand, or "
            "suppliers' true inventories/production/costs. Allocate no more than offers and aggregate "
            "capacity."
        ),
        "background": "",
    },
]


def bundle_simulation() -> SimulationConfig:
    return SimulationConfig.from_json_values(simulation_dict(EXPERIMENT_ID))


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
    config = bundle_simulation()
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
    config = bundle_simulation()
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
    config = bundle_simulation()
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
    config = bundle_simulation()
    phases = config.protocol_parameters["phases"]
    supply = [phase for phase in phases if phase["name"] == "d1_supply"]
    assert len(supply) == 1 and set(supply[0]["actor_ids"]) == {SUPPLIER_A, SUPPLIER_B}
    for supplier in (SUPPLIER_A, SUPPLIER_B):
        other = SUPPLIER_B if supplier == SUPPLIER_A else SUPPLIER_A
        permissions = PERMISSIONS[supplier]
        assert other not in json.dumps(permissions)
        assert "pending_offers" not in permissions["public_fields"]


def test_safe_fallback_payloads_pass_mechanism_legality():
    config = bundle_simulation().world
    cases = [
        (
            "d1_order",
            0,
            (
                {
                    "actor_id": MANUFACTURER,
                    "kind": "order",
                    "payload": SAFE_FALLBACKS[MANUFACTURER]["order"],
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
                    "payload": SAFE_FALLBACKS[SUPPLIER_A]["offer"],
                },
                {
                    "actor_id": SUPPLIER_B,
                    "kind": "offer",
                    "payload": SAFE_FALLBACKS[SUPPLIER_B]["offer"],
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
                    "payload": SAFE_FALLBACKS[LOGISTICS]["allocate"],
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
                    "payload": SAFE_FALLBACKS[MANUFACTURER]["produce"],
                },
            ),
        ),
    ]

    for phase, tick, payloads in cases:
        state = state_at(phase, tick)
        actions = tuple(Action.model_validate(item) for item in payloads)
        assert MECH.validate_actions(config, state, actions) is None


def test_every_supplied_parameter_is_preserved():
    simulation = bundle_simulation().model_dump(mode="json")

    for name, target_path, value in EXPECTED_SUPPLIED:
        assert same_json(resolve_pointer(simulation, target_path), value), name


def test_actor_behaviors_preserved_verbatim():
    simulation = bundle_simulation()
    actors = {actor.id: actor for actor in simulation.world.actors}
    assert ACTOR_BEHAVIORS == {behavior["actor_id"]: behavior for behavior in EXPECTED_BEHAVIORS}
    for behavior in EXPECTED_BEHAVIORS:
        assert actors[behavior["actor_id"]].policy_parameters["behavior"] == behavior
