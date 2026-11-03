"""Timing: one-day transit, flood window, determinism, evaluate consistency."""

from experiment_extension.mechanism import SupplyChainMechanism
from helpers import mechanism_and_state as _base_setup
from helpers import step_day

from components.protocols.sequential import SequentialProtocol
from simulation_core.types import Action, SimulationConfig, WorldState

ORDER = {"order_a": 80, "order_b": 80, "priority_a": 0, "priority_b": 0}


def mechanism_and_state() -> tuple[SupplyChainMechanism, SimulationConfig, WorldState]:
    """Local setup: helper fixture plus draft-config validation through a fresh mechanism."""
    mechanism, config, state = _base_setup()
    assert SupplyChainMechanism().validate_config(config.world) is None
    return mechanism, config, state


SUPPLY = {"produce": 80, "fulfill": 80, "ship_request": 80, "priority": 0}
PRODUCE = {"produce": 80}


def _allocate_for(capacity: int) -> dict[str, int]:
    half = capacity // 2
    return {"allocate_a": min(80, half), "allocate_b": min(80, capacity - min(80, half))}


def _produce_for(state: WorldState) -> dict[str, int]:
    facts = state.private["manufacturer"].facts
    comp_a = facts["comp_a"]
    comp_b = facts["comp_b"]
    capacity = facts["capacity"]
    assert isinstance(comp_a, int) and isinstance(comp_b, int) and isinstance(capacity, int)
    return {"produce": min(80, comp_a, comp_b, capacity)}


def _run_nine_days() -> list[dict[str, object]]:
    mechanism, config, state = mechanism_and_state()
    snapshots = []
    for _ in range(9):
        capacity = state.public["capacity"]
        assert isinstance(capacity, int)
        produce = _produce_for(state)
        state = step_day(
            mechanism, config, state, ORDER, SUPPLY, SUPPLY, _allocate_for(capacity), produce
        )
        snapshots.append(
            {
                "tick": state.tick,
                "phase": state.phase,
                "public": dict(state.public),
                "private": {aid: dict(item.facts) for aid, item in state.private.items()},
            }
        )
    return snapshots


def test_arrivals_land_next_day() -> None:
    mechanism, config, state = mechanism_and_state()
    assert isinstance(mechanism, SupplyChainMechanism)
    state = step_day(mechanism, config, state, ORDER, SUPPLY, SUPPLY, _allocate_for(200), PRODUCE)
    # Day-one dispatches are delivered before the day-two order observation:
    # closing 70 plus 80 arrivals, with an empty pipeline mid-horizon.
    assert state.phase == "d2_order"
    assert state.public["in_transit"] == {"A": 0, "B": 0}
    assert state.public["arrivals"] == {"A": 80, "B": 80}
    before_a = state.private["manufacturer"].facts["comp_a"]
    assert before_a == 150
    state = step_day(mechanism, config, state, ORDER, SUPPLY, SUPPLY, _allocate_for(200), PRODUCE)
    # Day-two arrivals (80/80 from day-one dispatches) were already in stock,
    # then 80 produced (closing 70) and day-two dispatches delivered.
    assert state.private["manufacturer"].facts["comp_a"] == 150
    assert state.public["arrivals"] == {"A": 80, "B": 80}
    assert state.public["in_transit"] == {"A": 0, "B": 0}


def test_order_observation_already_contains_arrivals() -> None:
    mechanism, config, state = mechanism_and_state()
    world = config.world
    state = step_day(mechanism, config, state, ORDER, SUPPLY, SUPPLY, _allocate_for(200), PRODUCE)
    assert state.phase == "d2_order"
    maker_before = state.private["manufacturer"].facts
    assert maker_before["comp_a"] == 150 and maker_before["comp_b"] == 150
    result = mechanism.transition(
        world, state, (Action(actor_id="manufacturer", kind="order", payload=dict(ORDER)),)
    )
    maker_after = result.private_updates["manufacturer"].facts
    # The ordering phase records orders only; stock is unchanged.
    assert maker_after["comp_a"] == 150 and maker_after["comp_b"] == 150
    assert maker_after["finished"] == maker_before["finished"]
    assert result.public["arrivals"] == {"A": 80, "B": 80}
    assert result.outcome.metrics["arrived_a"] == 80
    assert result.outcome.metrics["arrived_b"] == 80


def test_flood_onset_day_three_and_recovery_day_seven() -> None:
    mechanism, config, state = mechanism_and_state()
    timeline = []
    for _ in range(9):
        timeline.append((state.public["day"], state.public["capacity"], state.public["disrupted"]))
        capacity = state.public["capacity"]
        assert isinstance(capacity, int)
        state = step_day(
            mechanism,
            config,
            state,
            ORDER,
            SUPPLY,
            SUPPLY,
            _allocate_for(capacity),
            _produce_for(state),
        )
    assert timeline == [
        (1, 200, False),
        (2, 200, False),
        (3, 80, True),
        (4, 80, True),
        (5, 80, True),
        (6, 80, True),
        (7, 200, False),
        (8, 200, False),
        (9, 200, False),
    ]


def test_final_day_dispatches_stay_in_transit() -> None:
    mechanism, config, state = mechanism_and_state()
    for _ in range(9):
        capacity = state.public["capacity"]
        assert isinstance(capacity, int)
        state = step_day(
            mechanism,
            config,
            state,
            ORDER,
            SUPPLY,
            SUPPLY,
            _allocate_for(capacity),
            _produce_for(state),
        )
    assert state.tick == 36
    assert state.phase == "finished"
    assert state.public["day"] == 9
    assert state.public["in_transit"] == {"A": 80, "B": 80}
    assert state.public["arrivals"] == {"A": 80, "B": 80}  # day-eight dispatches


def test_fixed_sequence_is_deterministic() -> None:
    first = _run_nine_days()
    second = _run_nine_days()
    assert first == second
    assert len(first) == 9
    assert first[-1]["phase"] == "finished"


def test_evaluate_matches_transition() -> None:
    mechanism, config, state = mechanism_and_state()
    world = config.world
    protocol = SequentialProtocol(dict(config.protocol_parameters))
    for _ in range(2):
        capacity = state.public["capacity"]
        assert isinstance(capacity, int)
        batches = (
            (Action(actor_id="manufacturer", kind="order", payload=dict(ORDER)),),
            (
                Action(actor_id="supplier_a", kind="supply", payload=dict(SUPPLY)),
                Action(actor_id="supplier_b", kind="supply", payload=dict(SUPPLY)),
            ),
            (
                Action(
                    actor_id="logistics",
                    kind="allocate",
                    payload=dict(_allocate_for(capacity)),
                ),
            ),
            (Action(actor_id="manufacturer", kind="produce", payload=dict(PRODUCE)),),
        )
        for batch in batches:
            evaluated = mechanism.evaluate(world, state, batch)
            transition = mechanism.transition(world, state, batch)
            assert evaluated == transition.outcome
            state = WorldState(
                tick=state.tick + 1,
                phase=protocol.next_phase(world, state),
                public=transition.public,
                private=dict(transition.private_updates),
            )
