"""Hand-derived settlement arithmetic; every number below is computed by hand."""

from experiment_extension.mechanism import SupplyChainMechanism
from helpers import mechanism_and_state as _base_setup
from helpers import step_day

from simulation_core.types import Action, SimulationConfig, WorldState

ORDER = {"order_a": 80, "order_b": 80, "priority_a": 0, "priority_b": 0}


def mechanism_and_state() -> tuple[SupplyChainMechanism, SimulationConfig, WorldState]:
    """Local setup: helper fixture plus draft-config validation through a fresh mechanism."""
    mechanism, config, state = _base_setup()
    assert SupplyChainMechanism().validate_config(config.world) is None
    return mechanism, config, state


SUPPLY = {"produce": 80, "fulfill": 80, "ship_request": 80, "priority": 0}
ALLOCATE = {"allocate_a": 80, "allocate_b": 80}
PRODUCE = {"produce": 80}


def test_hand_derived_day_one_settlement() -> None:
    mechanism, config, state = mechanism_and_state()
    assert isinstance(mechanism, SupplyChainMechanism)
    world = config.world
    before = state.model_dump(mode="json")
    outcome = mechanism.evaluate(
        world,
        state,
        (Action(actor_id="manufacturer", kind="order", payload=dict(ORDER)),),
    )
    assert outcome.payoffs == {"manufacturer": 0.0}
    assert state.model_dump(mode="json") == before
    state = step_day(mechanism, config, state, ORDER, SUPPLY, SUPPLY, ALLOCATE, PRODUCE)
    assert state.public["day"] == 2
    assert state.public["in_transit"] == {"A": 80, "B": 80}
    maker = state.private["manufacturer"].facts
    assert maker["comp_a"] == 70  # 150 + 0 arrivals - 80 produced
    assert maker["comp_b"] == 70
    assert maker["finished"] == 0
    assert maker["backlog_a"] == 0 and maker["backlog_b"] == 0
    assert maker["cumulative_sold"] == 80
    assert maker["cumulative_lost_sales"] == 0
    assert state.private["supplier_a"].facts["inventory"] == 200  # 200 + 80 - 80
    assert state.private["supplier_b"].facts["inventory"] == 200
    # Revenue 80*100=8000; procurement 160*20=3200; assembly 80*15=1200;
    # freight 160*5=800; holding (70+70)*1+0*2=140. Profit 2660.
    assert maker["cumulative_revenue"] == 8000.0
    assert maker["cumulative_cost"] == 3200.0 + 1200.0 + 800.0 + 140.0
    for supplier in ("supplier_a", "supplier_b"):
        facts = state.private[supplier].facts
        # Revenue 80*20=1600; production 80*12=960; holding 200*0.5=100.
        assert facts["cumulative_revenue"] == 1600.0
        assert facts["cumulative_cost"] == 960.0 + 100.0
        assert facts["cumulative_dispatched"] == 80
    carrier = state.private["logistics"].facts
    assert carrier["cumulative_revenue"] == 800.0  # 160*5
    assert carrier["cumulative_cost"] == 480.0  # 160*3


def test_transfer_cancellation_identity() -> None:
    mechanism, config, state = mechanism_and_state()
    world = config.world
    state = step_day(mechanism, config, state, ORDER, SUPPLY, SUPPLY, ALLOCATE, PRODUCE)
    assert state.tick == 4
    transition = mechanism.transition(
        world,
        state,
        (Action(actor_id="manufacturer", kind="order", payload=dict(ORDER)),),
    )
    assert transition.outcome.payoffs == {"manufacturer": 0.0}
    # Recompute day-one consolidated profit from real costs only:
    # 8000 - (assembly 1200 + maker holding 140 + production 960*2 + supplier
    # holding 100*2 + transport operating 480) = 4060.
    maker = state.private["manufacturer"].facts
    assert maker["cumulative_revenue"] - maker["cumulative_cost"] == 2660.0
    profits = [
        maker["cumulative_revenue"] - maker["cumulative_cost"],
        state.private["supplier_a"].facts["cumulative_revenue"]
        - state.private["supplier_a"].facts["cumulative_cost"],
        state.private["supplier_b"].facts["cumulative_revenue"]
        - state.private["supplier_b"].facts["cumulative_cost"],
        state.private["logistics"].facts["cumulative_revenue"]
        - state.private["logistics"].facts["cumulative_cost"],
    ]
    assert profits == [2660.0, 540.0, 540.0, 320.0]
    assert sum(profits) == 4060.0
    assert 8000.0 - (1200.0 + 140.0 + 960.0 + 100.0 + 960.0 + 100.0 + 480.0) == 4060.0


def test_holding_cost_uses_closing_stock() -> None:
    mechanism, config, state = mechanism_and_state()
    low = step_day(
        mechanism,
        config,
        state,
        ORDER,
        SUPPLY,
        SUPPLY,
        ALLOCATE,
        {"produce": 60},
    )
    maker = low.private["manufacturer"].facts
    # Closing 180 components + 0 finished: holding 180.
    assert maker["comp_a"] == 90 and maker["finished"] == 0
    assert maker["cumulative_cost"] == 3200.0 + 900.0 + 800.0 + 180.0
    assert maker["cumulative_revenue"] == 6000.0
    assert maker["cumulative_lost_sales"] == 20


def test_dispatch_timing_of_charges() -> None:
    mechanism, config, state = mechanism_and_state()
    state = step_day(
        mechanism,
        config,
        state,
        ORDER,
        SUPPLY,
        SUPPLY,
        {"allocate_a": 0, "allocate_b": 0},
        PRODUCE,
    )
    maker = state.private["manufacturer"].facts
    # Nothing dispatched: no procurement, no freight; assembly and holding only.
    assert maker["cumulative_revenue"] == 8000.0
    assert maker["cumulative_cost"] == 0.0 + 1200.0 + 0.0 + 140.0
    assert state.private["supplier_a"].facts["cumulative_revenue"] == 0.0
    assert state.private["logistics"].facts["cumulative_revenue"] == 0.0
    assert state.public["in_transit"] == {"A": 0, "B": 0}


def test_opening_stock_is_sunk() -> None:
    mechanism, config, state = mechanism_and_state()
    idle_supply = {"produce": 0, "fulfill": 0, "ship_request": 0, "priority": 0}
    state = step_day(
        mechanism,
        config,
        state,
        {"order_a": 0, "order_b": 0, "priority_a": 0, "priority_b": 0},
        idle_supply,
        idle_supply,
        {"allocate_a": 0, "allocate_b": 0},
        {"produce": 0},
    )
    # No opening-stock revaluation: suppliers pay holding on 200 units only.
    assert state.private["supplier_a"].facts["cumulative_cost"] == 100.0
    assert state.private["supplier_b"].facts["cumulative_cost"] == 100.0
    maker = state.private["manufacturer"].facts
    assert maker["cumulative_cost"] == 300.0  # holding on 150+150 only
    assert maker["cumulative_lost_sales"] == 80


def test_lost_sales_never_backlogged() -> None:
    mechanism, config, state = mechanism_and_state()
    state = step_day(mechanism, config, state, ORDER, SUPPLY, SUPPLY, ALLOCATE, {"produce": 0})
    assert state.private["manufacturer"].facts["cumulative_lost_sales"] == 80
    state = step_day(mechanism, config, state, ORDER, SUPPLY, SUPPLY, ALLOCATE, PRODUCE)
    # Day-two demand is a fresh 80; day-one losses do not carry forward.
    assert state.private["manufacturer"].facts["cumulative_sold"] == 80
    assert state.private["manufacturer"].facts["cumulative_lost_sales"] == 80
    assert state.private["manufacturer"].facts["finished"] == 0
