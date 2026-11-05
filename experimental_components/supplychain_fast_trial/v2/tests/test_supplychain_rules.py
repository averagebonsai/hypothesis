"""Mechanism rules: hand-derived day cases, rejections and boundaries."""

import copy

import pytest
from experiment_extension.supplychain import (
    LOGISTICS,
    MANUFACTURER,
    SUPPLIER_A,
    SUPPLIER_B,
    SupplyChainMechanism,
    capacity_for_day,
)
from support import (
    INITIAL_PUBLIC,
    MANUFACTURER_FACTS,
    PARAMS,
    SUPPLIER_FACTS,
    make_registry,
    scripted_config,
)

from simulation_core.types import Action, PrivateState, WorldState

MECH = SupplyChainMechanism()


def make_state(public=None, mfg=None, sup_a=None, sup_b=None, tick=0, phase="d1_order"):
    public_state = copy.deepcopy(INITIAL_PUBLIC)
    if public:
        public_state.update(copy.deepcopy(public))
    return WorldState(
        tick=tick,
        phase=phase,
        public=public_state,
        private={
            MANUFACTURER: PrivateState(facts={**MANUFACTURER_FACTS, **(mfg or {})}, memory={}),
            SUPPLIER_A: PrivateState(facts={**SUPPLIER_FACTS, **(sup_a or {})}, memory={}),
            SUPPLIER_B: PrivateState(facts={**SUPPLIER_FACTS, **(sup_b or {})}, memory={}),
            LOGISTICS: PrivateState(
                facts={
                    "request_a": 0,
                    "request_b": 0,
                    "cum_dispatched": 0,
                    "cum_revenue": 0.0,
                    "cum_operating": 0.0,
                    "cum_unused": 0,
                    "last_alloc_a": 0,
                    "last_alloc_b": 0,
                    "day": 1,
                },
                memory={},
            ),
        },
    )


def config():
    return scripted_config().world


def test_hand_derived_day_one_transitions():
    """Day 1 by hand: order 80/80, produce 100 offer 80, ship 80/80, make 80."""
    # Order phase.
    state = make_state(phase="d1_order")
    order = Action(
        actor_id=MANUFACTURER,
        kind="order",
        payload={"order_a": 80, "order_b": 80, "priority": "none"},
    )
    MECH.validate_actions(config(), state, (order,))
    result = MECH.transition(config(), state, (order,))
    assert result.private_updates[MANUFACTURER].facts["backlog_a"] == 80
    assert result.private_updates[SUPPLIER_A].facts["backlog"] == 80
    assert result.public["backlogs"] == {"supplier_a": 80, "supplier_b": 80}
    assert state.public["backlogs"] == {"supplier_a": 0, "supplier_b": 0}

    # Supply phase: produce 100 each, offer 80 each.
    supply_state = WorldState(
        tick=1, phase="d1_supply", public=result.public, private=result.private_updates
    )
    offers = (
        Action(
            actor_id=SUPPLIER_A,
            kind="offer",
            payload={"produce": 100, "offer": 80, "priority_request": False},
        ),
        Action(
            actor_id=SUPPLIER_B,
            kind="offer",
            payload={"produce": 100, "offer": 80, "priority_request": False},
        ),
    )
    MECH.validate_actions(config(), supply_state, offers)
    outcome = MECH.evaluate(config(), supply_state, offers)
    assert outcome.payoffs[SUPPLIER_A] == -1200.0
    assert outcome.payoffs[SUPPLIER_B] == -1200.0
    result2 = MECH.transition(config(), supply_state, offers)
    assert result2.private_updates[SUPPLIER_A].facts["inventory"] == 300
    assert result2.public["pending_offers"] == {"supplier_a": 80, "supplier_b": 80}

    # Ship phase: 80/80 within the 200 capacity.
    ship_state = WorldState(
        tick=2, phase="d1_ship", public=result2.public, private=result2.private_updates
    )
    alloc = Action(actor_id=LOGISTICS, kind="allocate", payload={"alloc_a": 80, "alloc_b": 80})
    MECH.validate_actions(config(), ship_state, (alloc,))
    outcome = MECH.evaluate(config(), ship_state, (alloc,))
    assert outcome.payoffs[SUPPLIER_A] == 1600.0
    assert outcome.payoffs[SUPPLIER_B] == 1600.0
    assert outcome.payoffs[MANUFACTURER] == -(20.0 * 160 + 5.0 * 160)
    assert outcome.payoffs[LOGISTICS] == 5.0 * 160 - 3.0 * 160
    result3 = MECH.transition(config(), ship_state, (alloc,))
    assert result3.private_updates[SUPPLIER_A].facts["inventory"] == 220
    assert result3.private_updates[MANUFACTURER].facts["backlog_a"] == 0
    assert result3.public["in_transit"] == [
        {"component": "A", "quantity": 80, "arrival_day": 2},
        {"component": "B", "quantity": 80, "arrival_day": 2},
    ]

    # Make phase: build 80, sell 80, no lost sales.
    producing = WorldState(
        tick=3, phase="d1_make", public=result3.public, private=result3.private_updates
    )
    make = Action(actor_id=MANUFACTURER, kind="produce", payload={"produce": 80})
    MECH.validate_actions(config(), producing, (make,))
    outcome = MECH.evaluate(config(), producing, (make,))
    assert outcome.payoffs[MANUFACTURER] == 100.0 * 80 - 15.0 * 80 - 1.0 * 140 - 2.0 * 0
    assert outcome.metrics == {"day": 1, "slot": "make", "sold": 80, "lost": 0}
    result4 = MECH.transition(config(), producing, (make,))
    mfg = result4.private_updates[MANUFACTURER].facts
    assert (mfg["comp_a"], mfg["comp_b"], mfg["finished_goods"]) == (70 + 80, 70 + 80, 0)
    assert result4.public["arrivals_today"] == {"A": 80, "B": 80}
    assert result4.public["day"] == 2
    assert result4.public["capacity"] == 200
    assert result4.public["history"][0]["sold"] == 80


def test_rejections_cover_each_constraint():
    state = make_state(phase="d1_supply", public={"backlogs": {"supplier_a": 10, "supplier_b": 10}})
    over_capacity = Action(
        actor_id=SUPPLIER_A,
        kind="offer",
        payload={"produce": 101, "offer": 0, "priority_request": False},
    )
    with pytest.raises(ValueError, match="daily capacity"):
        MECH.validate_actions(
            config(),
            state,
            (
                over_capacity,
                Action(
                    actor_id=SUPPLIER_B,
                    kind="offer",
                    payload={"produce": 0, "offer": 0, "priority_request": False},
                ),
            ),
        )
    over_backlog = Action(
        actor_id=SUPPLIER_A,
        kind="offer",
        payload={"produce": 0, "offer": 11, "priority_request": False},
    )
    with pytest.raises(ValueError, match="backlog"):
        MECH.validate_actions(
            config(),
            state,
            (
                over_backlog,
                Action(
                    actor_id=SUPPLIER_B,
                    kind="offer",
                    payload={"produce": 0, "offer": 0, "priority_request": False},
                ),
            ),
        )
    over_stock = Action(
        actor_id=SUPPLIER_A,
        kind="offer",
        payload={"produce": 0, "offer": 201, "priority_request": False},
    )
    with pytest.raises(ValueError, match="backlog|physically"):
        MECH.validate_actions(
            config(),
            state,
            (
                over_stock,
                Action(
                    actor_id=SUPPLIER_B,
                    kind="offer",
                    payload={"produce": 0, "offer": 0, "priority_request": False},
                ),
            ),
        )

    ship = make_state(
        phase="d1_ship",
        public={"pending_offers": {"supplier_a": 50, "supplier_b": 50}, "capacity": 80},
    )
    with pytest.raises(ValueError, match="offers"):
        MECH.validate_actions(
            config(),
            ship,
            (Action(actor_id=LOGISTICS, kind="allocate", payload={"alloc_a": 51, "alloc_b": 0}),),
        )
    with pytest.raises(ValueError, match="capacity"):
        MECH.validate_actions(
            config(),
            ship,
            (Action(actor_id=LOGISTICS, kind="allocate", payload={"alloc_a": 50, "alloc_b": 50}),),
        )
    with pytest.raises(ValueError, match="kind|phase"):
        MECH.validate_actions(
            config(), ship, (Action(actor_id=MANUFACTURER, kind="produce", payload={"produce": 0}),)
        )

    make = make_state(phase="d1_make")
    with pytest.raises(ValueError, match="daily capacity"):
        MECH.validate_actions(
            config(),
            make,
            (Action(actor_id=MANUFACTURER, kind="produce", payload={"produce": 101}),),
        )
    low_stock = make_state(phase="d1_make", mfg={"comp_a": 50, "comp_b": 50})
    with pytest.raises(ValueError, match="component inventory"):
        MECH.validate_actions(
            config(),
            low_stock,
            (Action(actor_id=MANUFACTURER, kind="produce", payload={"produce": 80}),),
        )


def test_boundary_zero_capacity_empty_stock_and_oversized_requests():
    ship = make_state(
        phase="d3_ship",
        public={"pending_offers": {"supplier_a": 60, "supplier_b": 60}, "capacity": 0},
    )
    MECH.validate_actions(
        config(),
        ship,
        (Action(actor_id=LOGISTICS, kind="allocate", payload={"alloc_a": 0, "alloc_b": 0}),),
    )
    with pytest.raises(ValueError, match="capacity"):
        MECH.validate_actions(
            config(),
            ship,
            (Action(actor_id=LOGISTICS, kind="allocate", payload={"alloc_a": 1, "alloc_b": 0}),),
        )

    empty = make_state(phase="d1_make", mfg={"comp_a": 0, "comp_b": 0})
    MECH.validate_actions(
        config(), empty, (Action(actor_id=MANUFACTURER, kind="produce", payload={"produce": 0}),)
    )
    with pytest.raises(ValueError, match="component inventory"):
        MECH.validate_actions(
            config(),
            empty,
            (Action(actor_id=MANUFACTURER, kind="produce", payload={"produce": 1}),),
        )

    poor = make_state(
        phase="d1_supply",
        public={"backlogs": {"supplier_a": 500, "supplier_b": 500}},
        sup_a={"backlog": 500},
        sup_b={"backlog": 500},
    )
    with pytest.raises(ValueError, match="physically"):
        MECH.validate_actions(
            config(),
            poor,
            (
                Action(
                    actor_id=SUPPLIER_A,
                    kind="offer",
                    payload={"produce": 100, "offer": 500, "priority_request": False},
                ),
                Action(
                    actor_id=SUPPLIER_B,
                    kind="offer",
                    payload={"produce": 0, "offer": 0, "priority_request": False},
                ),
            ),
        )


def test_capacity_schedule_boundaries():
    assert capacity_for_day(PARAMS["capacity_schedule"], 1) == 200
    assert capacity_for_day(PARAMS["capacity_schedule"], 2) == 200
    assert capacity_for_day(PARAMS["capacity_schedule"], 3) == 80
    assert capacity_for_day(PARAMS["capacity_schedule"], 6) == 80
    assert capacity_for_day(PARAMS["capacity_schedule"], 7) == 200
    assert capacity_for_day(PARAMS["capacity_schedule"], 9) == 200
    with pytest.raises(ValueError, match="covers day"):
        capacity_for_day(PARAMS["capacity_schedule"], 10)


def test_deterministic_replay_matches():
    kwargs = {"phase": "d1_order"}
    first = MECH.transition(
        config(),
        make_state(**kwargs),
        (
            Action(
                actor_id=MANUFACTURER,
                kind="order",
                payload={"order_a": 80, "order_b": 80, "priority": "A"},
            ),
        ),
    )
    second = MECH.transition(
        config(),
        make_state(**kwargs),
        (
            Action(
                actor_id=MANUFACTURER,
                kind="order",
                payload={"order_a": 80, "order_b": 80, "priority": "A"},
            ),
        ),
    )
    assert first == second


def test_registry_configuration_validates():
    registry = make_registry()
    assert registry.mechanisms["test.supplychain.v1"] is SupplyChainMechanism
    assert registry.validate_config(scripted_config()) is None
