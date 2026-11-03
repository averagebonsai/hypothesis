"""Rejection of infeasible actions and boundary behavior."""

import pytest
from experiment_extension.mechanism import SupplyChainMechanism
from experiment_extension.schemas import (
    AllocateAction,
    OrderAction,
    ProduceAction,
    SupplyAction,
)
from helpers import draft_data, step_day
from helpers import mechanism_and_state as _base_setup

from components.protocols.sequential import SequentialProtocol
from simulation_core.types import Action, SimulationConfig, WorldState

ORDER = {"order_a": 80, "order_b": 80, "priority_a": 0, "priority_b": 0}
SUPPLY = {"produce": 80, "fulfill": 80, "ship_request": 80, "priority": 0}
ALLOCATE = {"allocate_a": 80, "allocate_b": 80}
PRODUCE = {"produce": 80}


def mechanism_and_state() -> tuple[SupplyChainMechanism, SimulationConfig, WorldState]:
    """Local setup: helper fixture plus draft-config validation through a fresh mechanism."""
    mechanism, config, state = _base_setup()
    assert SupplyChainMechanism().validate_config(config.world) is None
    return mechanism, config, state


def test_schemas_reject_negative_fractional_and_missing() -> None:
    assert OrderAction(order_a=1, order_b=2, priority_a=3, priority_b=4).order_b == 2
    for cls, good in (
        (OrderAction, ORDER),
        (ProduceAction, PRODUCE),
        (SupplyAction, SUPPLY),
        (AllocateAction, ALLOCATE),
    ):
        cls.from_json_values(good)
        for field in good:
            bad = dict(good)
            bad[field] = -1
            with pytest.raises(ValueError, match="greater than or equal to 0"):
                cls.from_json_values(bad)
            bad[field] = 1.5
            with pytest.raises(ValueError, match="integer"):
                cls.from_json_values(bad)
        short = dict(good)
        short.pop(next(iter(short)))
        with pytest.raises(ValueError, match="Field required"):
            cls.from_json_values(short)


def test_rejects_over_capacity_production() -> None:
    mechanism, config, state = mechanism_and_state()
    world = config.world
    state = step_day(mechanism, config, state, ORDER, SUPPLY, SUPPLY, ALLOCATE, PRODUCE)
    assert state.phase == "d2_order"
    with pytest.raises(ValueError, match="above capacity"):
        mechanism.validate_actions(
            world,
            WorldState(
                tick=state.tick + 1,
                phase="d2_supply",
                public={**state.public, "order_a": 80, "order_b": 80},
                private=dict(state.private),
            ),
            (
                Action(
                    actor_id="supplier_a",
                    kind="supply",
                    payload={"produce": 101, "fulfill": 0, "ship_request": 0, "priority": 0},
                ),
                Action(
                    actor_id="supplier_b",
                    kind="supply",
                    payload={"produce": 0, "fulfill": 0, "ship_request": 0, "priority": 0},
                ),
            ),
        )


def test_rejects_production_above_stock_or_assembly_capacity() -> None:
    mechanism, config, state = mechanism_and_state()
    world = config.world
    # Stock bound: 150 on hand, assembly capacity 100.
    with pytest.raises(ValueError, match="feasible"):
        mechanism.validate_actions(
            world,
            WorldState(
                tick=3, phase="d1_settle", public=dict(state.public), private=dict(state.private)
            ),
            (Action(actor_id="manufacturer", kind="produce", payload={"produce": 101}),),
        )
    with pytest.raises(ValueError, match="feasible"):
        mechanism.validate_actions(
            world,
            WorldState(
                tick=3, phase="d1_settle", public=dict(state.public), private=dict(state.private)
            ),
            (Action(actor_id="manufacturer", kind="produce", payload={"produce": 151}),),
        )
    mechanism.validate_actions(
        world,
        WorldState(
            tick=3, phase="d1_settle", public=dict(state.public), private=dict(state.private)
        ),
        (Action(actor_id="manufacturer", kind="produce", payload={"produce": 100}),),
    )


def test_rejects_offer_above_stock_and_acceptance_above_backlog() -> None:
    mechanism, config, state = mechanism_and_state()
    world = config.world
    state = step_day(mechanism, config, state, ORDER, SUPPLY, SUPPLY, ALLOCATE, PRODUCE)
    supply_state = WorldState(
        tick=state.tick + 1,
        phase="d2_supply",
        public={**state.public, "order_a": 80, "order_b": 80},
        private=dict(state.private),
    )
    # Backlog is 80; accepting 81 must fail.
    with pytest.raises(ValueError, match="above backlog"):
        mechanism.validate_actions(
            world,
            supply_state,
            (
                Action(
                    actor_id="supplier_a",
                    kind="supply",
                    payload={"produce": 0, "fulfill": 81, "ship_request": 0, "priority": 0},
                ),
                Action(
                    actor_id="supplier_b",
                    kind="supply",
                    payload={"produce": 0, "fulfill": 0, "ship_request": 0, "priority": 0},
                ),
            ),
        )
    # Stock is 200 + 0 produced; offering 500 must fail.
    with pytest.raises(ValueError, match="above available stock"):
        mechanism.validate_actions(
            world,
            supply_state,
            (
                Action(
                    actor_id="supplier_a",
                    kind="supply",
                    payload={"produce": 0, "fulfill": 0, "ship_request": 500, "priority": 0},
                ),
                Action(
                    actor_id="supplier_b",
                    kind="supply",
                    payload={"produce": 0, "fulfill": 0, "ship_request": 0, "priority": 0},
                ),
            ),
        )


def test_rejects_offer_above_acceptance() -> None:
    mechanism, config, state = mechanism_and_state()
    world = config.world
    state = step_day(mechanism, config, state, ORDER, SUPPLY, SUPPLY, ALLOCATE, PRODUCE)
    order_result = mechanism.transition(
        world,
        state,
        (Action(actor_id="manufacturer", kind="order", payload=dict(ORDER)),),
    )
    supply_state = WorldState(
        tick=state.tick + 1,
        phase="d2_supply",
        public=order_result.public,
        private=dict(order_result.private_updates),
    )
    assert supply_state.private["supplier_a"].facts["backlog"] == 80
    # Offering within stock but above the same-day acceptance must fail.
    with pytest.raises(ValueError, match="above accepted"):
        mechanism.validate_actions(
            world,
            supply_state,
            (
                Action(
                    actor_id="supplier_a",
                    kind="supply",
                    payload={"produce": 0, "fulfill": 80, "ship_request": 81, "priority": 0},
                ),
                Action(
                    actor_id="supplier_b",
                    kind="supply",
                    payload={"produce": 0, "fulfill": 0, "ship_request": 0, "priority": 0},
                ),
            ),
        )
    # Zero accepted orders prohibit any shipment request.
    with pytest.raises(ValueError, match="above accepted"):
        mechanism.validate_actions(
            world,
            supply_state,
            (
                Action(
                    actor_id="supplier_a",
                    kind="supply",
                    payload={"produce": 0, "fulfill": 0, "ship_request": 1, "priority": 0},
                ),
                Action(
                    actor_id="supplier_b",
                    kind="supply",
                    payload={"produce": 0, "fulfill": 0, "ship_request": 0, "priority": 0},
                ),
            ),
        )
    mechanism.validate_actions(
        world,
        supply_state,
        (
            Action(
                actor_id="supplier_a",
                kind="supply",
                payload={"produce": 0, "fulfill": 80, "ship_request": 80, "priority": 0},
            ),
            Action(
                actor_id="supplier_b",
                kind="supply",
                payload={"produce": 0, "fulfill": 0, "ship_request": 0, "priority": 0},
            ),
        ),
    )


def test_rejects_allocation_above_stock_or_backlog() -> None:
    mechanism, config, state = mechanism_and_state()
    world = config.world
    state = step_day(mechanism, config, state, ORDER, SUPPLY, SUPPLY, ALLOCATE, PRODUCE)
    assert state.private["supplier_a"].facts["backlog"] == 0
    assert state.private["supplier_a"].facts["inventory"] == 200
    ship_state = WorldState(
        tick=state.tick + 2,
        phase="d2_ship",
        public={**state.public, "offer_a": 250, "offer_b": 0, "capacity": 300},
        private=dict(state.private),
    )
    with pytest.raises(ValueError, match="available stock"):
        mechanism.validate_actions(
            world,
            ship_state,
            (
                Action(
                    actor_id="logistics",
                    kind="allocate",
                    payload={"allocate_a": 201, "allocate_b": 0},
                ),
            ),
        )
    # Zero outstanding orders prohibit any allocation even when offered.
    with pytest.raises(ValueError, match="outstanding backlog"):
        mechanism.validate_actions(
            world,
            ship_state,
            (
                Action(
                    actor_id="logistics",
                    kind="allocate",
                    payload={"allocate_a": 1, "allocate_b": 0},
                ),
            ),
        )


def test_settle_dispatch_matches_allocation_and_backlog_exactly() -> None:
    mechanism, config, state = mechanism_and_state()
    world = config.world
    state = step_day(mechanism, config, state, ORDER, SUPPLY, SUPPLY, ALLOCATE, PRODUCE)
    maker = state.private["manufacturer"].facts
    # Exact decrement: 80 ordered minus 80 dispatched leaves zero, never clamped.
    assert maker["backlog_a"] == 0 and maker["backlog_b"] == 0
    assert state.private["supplier_a"].facts["backlog"] == 0
    assert state.private["supplier_a"].facts["inventory"] == 200
    bad_settle = WorldState(
        tick=state.tick + 3,
        phase="d2_settle",
        public={**state.public, "allocation_a": 10, "allocation_b": 0},
        private=dict(state.private),
    )
    with pytest.raises(ValueError, match="outstanding backlog"):
        mechanism.validate_actions(
            world,
            bad_settle,
            (Action(actor_id="manufacturer", kind="produce", payload={"produce": 0}),),
        )


def test_rejects_allocation_above_offer_or_capacity() -> None:
    mechanism, config, state = mechanism_and_state()
    world = config.world
    state = step_day(mechanism, config, state, ORDER, SUPPLY, SUPPLY, ALLOCATE, PRODUCE)
    ship_state = WorldState(
        tick=state.tick + 2,
        phase="d2_ship",
        public={**state.public, "offer_a": 80, "offer_b": 80},
        private=dict(state.private),
    )
    with pytest.raises(ValueError, match="exceeds offer"):
        mechanism.validate_actions(
            world,
            ship_state,
            (
                Action(
                    actor_id="logistics",
                    kind="allocate",
                    payload={"allocate_a": 81, "allocate_b": 0},
                ),
            ),
        )
    big_offer = WorldState(
        tick=state.tick + 2,
        phase="d2_ship",
        public={**state.public, "offer_a": 200, "offer_b": 200},
        private=dict(state.private),
    )
    with pytest.raises(ValueError, match="exceeds capacity"):
        mechanism.validate_actions(
            world,
            big_offer,
            (
                Action(
                    actor_id="logistics",
                    kind="allocate",
                    payload={"allocate_a": 150, "allocate_b": 150},
                ),
            ),
        )
    mechanism.validate_actions(
        world,
        big_offer,
        (
            Action(
                actor_id="logistics", kind="allocate", payload={"allocate_a": 0, "allocate_b": 0}
            ),
        ),
    )


def test_flood_day_allocation_boundary() -> None:
    mechanism, config, state = mechanism_and_state()
    world = config.world
    state = step_day(mechanism, config, state, ORDER, SUPPLY, SUPPLY, ALLOCATE, PRODUCE)
    state = step_day(mechanism, config, state, ORDER, SUPPLY, SUPPLY, ALLOCATE, PRODUCE)
    assert state.public["day"] == 3
    assert state.public["capacity"] == 80
    assert state.public["disrupted"] is True
    big_supply = {"produce": 80, "fulfill": 80, "ship_request": 80, "priority": 0}
    state = step_day(
        mechanism,
        config,
        state,
        ORDER,
        big_supply,
        big_supply,
        {"allocate_a": 40, "allocate_b": 40},
        PRODUCE,
    )
    assert state.public["in_transit"] == {"A": 0, "B": 0}  # delivered before day-four orders
    assert state.public["arrivals"] == {"A": 40, "B": 40}
    with pytest.raises(ValueError, match="exceeds capacity"):
        mechanism.validate_actions(
            world,
            WorldState(
                tick=10,
                phase="d3_ship",
                public={
                    **state.public,
                    "day": 3,
                    "offer_a": 200,
                    "offer_b": 200,
                    "capacity": 80,
                },
                private=dict(state.private),
            ),
            (
                Action(
                    actor_id="logistics",
                    kind="allocate",
                    payload={"allocate_a": 80, "allocate_b": 80},
                ),
            ),
        )


def test_zero_capacity_variant() -> None:
    data = draft_data()["simulation"]
    assert isinstance(data, dict)
    world = data["world"]
    assert isinstance(world, dict)
    parameters = world["parameters"]
    assert isinstance(parameters, dict)
    parameters = dict(parameters)
    parameters["horizon_days"] = 1
    parameters["capacity_schedule"] = [{"start_day": 1, "end_day": 1, "capacity": 0}]
    world = dict(world)
    world["parameters"] = parameters
    public = dict(world["initial_public_state"])
    public["capacity"] = 0
    public["disrupted"] = False
    world["initial_public_state"] = public
    private = world["initial_private_state"]
    assert isinstance(private, dict)
    carrier = dict(private["logistics"])
    facts = dict(carrier["facts"])
    facts["capacity"] = 0
    carrier["facts"] = facts
    private = dict(private)
    private["logistics"] = carrier
    world["initial_private_state"] = private
    data = dict(data)
    data["world"] = world
    data["protocol_parameters"] = {
        "phases": [
            {"name": "d1_order", "actor_ids": ["manufacturer"]},
            {"name": "d1_supply", "actor_ids": ["supplier_a", "supplier_b"]},
            {"name": "d1_ship", "actor_ids": ["logistics"]},
            {"name": "d1_settle", "actor_ids": ["manufacturer"]},
        ],
        "terminal_phase": "finished",
    }
    data["assumptions"] = []
    variant = SimulationConfig.from_json_values(data)
    mechanism = SupplyChainMechanism()
    mechanism.validate_config(variant.world)
    protocol = SequentialProtocol(dict(variant.protocol_parameters))
    mechanism.validate_schedule(variant.world, protocol.decision_schedule(variant.world))
    from agent_tools.fixtures import fixture_state

    state = fixture_state(variant, protocol)
    mechanism.validate_state(variant.world, state)
    state = step_day(
        mechanism,
        variant,
        state,
        ORDER,
        SUPPLY,
        SUPPLY,
        {"allocate_a": 0, "allocate_b": 0},
        PRODUCE,
    )
    assert state.phase == "finished"
    assert state.public["in_transit"] == {"A": 0, "B": 0}
    with pytest.raises(ValueError, match="exceeds capacity"):
        mechanism.validate_actions(
            variant.world,
            WorldState(
                tick=2,
                phase="d1_ship",
                public={**state.public, "offer_a": 80, "offer_b": 80, "capacity": 0},
                private=dict(state.private),
            ),
            (
                Action(
                    actor_id="logistics",
                    kind="allocate",
                    payload={"allocate_a": 1, "allocate_b": 0},
                ),
            ),
        )


def test_empty_inventory_production() -> None:
    mechanism, config, state = mechanism_and_state()
    world = config.world
    idle = {"produce": 0, "fulfill": 0, "ship_request": 0, "priority": 0}
    none = {"allocate_a": 0, "allocate_b": 0}
    state = step_day(mechanism, config, state, ORDER, SUPPLY, SUPPLY, none, {"produce": 100})
    maker = state.private["manufacturer"].facts
    assert maker["comp_a"] == 50 and maker["finished"] == 20
    state = step_day(mechanism, config, state, ORDER, idle, idle, none, {"produce": 50})
    maker = state.private["manufacturer"].facts
    assert maker["comp_a"] == 0 and maker["comp_b"] == 0
    assert maker["finished"] == 0  # 20 + 50 produced, 70 sold, 10 lost
    assert maker["cumulative_lost_sales"] == 10
    with pytest.raises(ValueError, match="feasible"):
        mechanism.validate_actions(
            world,
            WorldState(
                tick=11,
                phase="d3_settle",
                public={**state.public, "day": 3},
                private=dict(state.private),
            ),
            (Action(actor_id="manufacturer", kind="produce", payload={"produce": 1}),),
        )
    mechanism.validate_actions(
        world,
        WorldState(
            tick=11,
            phase="d3_settle",
            public={**state.public, "day": 3},
            private=dict(state.private),
        ),
        (Action(actor_id="manufacturer", kind="produce", payload={"produce": 0}),),
    )


def test_unknown_actor_kind_and_terminal_rejected() -> None:
    mechanism, config, state = mechanism_and_state()
    world = config.world
    with pytest.raises(ValueError, match="exactly the manufacturer"):
        mechanism.validate_actions(
            world,
            state,
            (Action(actor_id="supplier_a", kind="supply", payload=dict(SUPPLY)),),
        )
    with pytest.raises(ValueError, match="kind 'order'"):
        mechanism.validate_actions(
            world,
            state,
            (Action(actor_id="manufacturer", kind="produce", payload=dict(PRODUCE)),),
        )
    terminal = WorldState(
        tick=36, phase="finished", public=dict(state.public), private=dict(state.private)
    )
    with pytest.raises(ValueError, match="terminal"):
        mechanism.validate_actions(
            world, terminal, (Action(actor_id="manufacturer", kind="order", payload=dict(ORDER)),)
        )


def test_declared_fallback_payloads_are_always_legal() -> None:
    mechanism, config, state = mechanism_and_state()
    world = config.world
    fallbacks = {
        actor.id: (actor.attributes["safe_fallback_actions"], actor.action_space.schemas)
        for actor in world.actors
    }
    assert set(fallbacks) == {"manufacturer", "supplier_a", "supplier_b", "logistics"}
    mechanism.validate_actions(
        world,
        state,
        (
            Action(
                actor_id="manufacturer",
                kind="order",
                payload=dict(fallbacks["manufacturer"][0]["order"]),
            ),
        ),
    )
    supply_state = WorldState(
        tick=1, phase="d1_supply", public=dict(state.public), private=dict(state.private)
    )
    mechanism.validate_actions(
        world,
        supply_state,
        (
            Action(
                actor_id="supplier_a",
                kind="supply",
                payload=dict(fallbacks["supplier_a"][0]["supply"]),
            ),
            Action(
                actor_id="supplier_b",
                kind="supply",
                payload=dict(fallbacks["supplier_b"][0]["supply"]),
            ),
        ),
    )
    ship_state = WorldState(
        tick=2, phase="d1_ship", public=dict(state.public), private=dict(state.private)
    )
    mechanism.validate_actions(
        world,
        ship_state,
        (
            Action(
                actor_id="logistics",
                kind="allocate",
                payload=dict(fallbacks["logistics"][0]["allocate"]),
            ),
        ),
    )
    settle_state = WorldState(
        tick=3, phase="d1_settle", public=dict(state.public), private=dict(state.private)
    )
    mechanism.validate_actions(
        world,
        settle_state,
        (
            Action(
                actor_id="manufacturer",
                kind="produce",
                payload=dict(fallbacks["manufacturer"][0]["produce"]),
            ),
        ),
    )
