"""Acceptance tests for the reusable second-price auction mechanism."""

import pytest
from auction_fixtures import (
    ACTORS,
    VALUATIONS,
    bid_actions,
    settle_expected,
    simulation_dict,
)
from experiment_extension.auction import SecondPriceMechanism

from agent_tools.fixtures import fixture_config, fixture_state
from components.protocols.simultaneous import SimultaneousProtocol
from simulation_core.observation import observe, permissions_for


def mechanism_fixture(actor_ids: tuple[str, ...] = ACTORS, valuations: dict | None = None):
    config = fixture_config(simulation_dict(actor_ids, valuations))
    protocol = SimultaneousProtocol({"rounds": 1})
    state = fixture_state(config, protocol)
    mechanism = SecondPriceMechanism()
    mechanism.validate_config(config.world)
    mechanism.validate_state(config.world, state)
    return mechanism, config, state


def test_mechanism_settles_second_price() -> None:
    mechanism, config, state = mechanism_fixture()
    bids = {"bidder_a": 70.0, "bidder_b": 65.0, "bidder_c": 40.0}
    actions = bid_actions(bids)
    mechanism.validate_actions(config.world, state, actions)
    outcome = mechanism.evaluate(config.world, state, actions)
    assert outcome.payoffs == {"bidder_a": 25.0, "bidder_b": 0.0, "bidder_c": 0.0}
    assert outcome.metrics["winner"] == "bidder_a"
    assert outcome.metrics["payment"] == 65.0
    assert outcome.metrics["bids"] == bids
    winner, payment, payoffs = settle_expected(bids, VALUATIONS, list(ACTORS))
    assert (outcome.metrics["winner"], outcome.metrics["payment"]) == (winner, payment)
    assert outcome.payoffs == payoffs


def test_mechanism_breaks_ties_by_config_order() -> None:
    mechanism, config, state = mechanism_fixture()
    bids = {"bidder_a": 60.0, "bidder_b": 60.0, "bidder_c": 40.0}
    outcome = mechanism.evaluate(config.world, state, bid_actions(bids))
    assert outcome.metrics["winner"] == "bidder_a"
    assert outcome.metrics["payment"] == 60.0
    assert outcome.payoffs == {"bidder_a": 30.0, "bidder_b": 0.0, "bidder_c": 0.0}
    three_way = {"bidder_a": 25.0, "bidder_b": 25.0, "bidder_c": 25.0}
    tied = mechanism.evaluate(config.world, state, bid_actions(three_way))
    assert tied.metrics["winner"] == "bidder_a"
    assert tied.metrics["payment"] == 25.0
    assert tied.payoffs["bidder_a"] == 65.0
    assert tied.payoffs["bidder_b"] == tied.payoffs["bidder_c"] == 0.0


def test_mechanism_allows_strategically_poor_bids() -> None:
    mechanism, config, state = mechanism_fixture()
    overbid = {"bidder_a": 70.0, "bidder_b": 65.0, "bidder_c": 100.0}
    mechanism.validate_actions(config.world, state, bid_actions(overbid))
    outcome = mechanism.evaluate(config.world, state, bid_actions(overbid))
    assert outcome.metrics["winner"] == "bidder_c"
    assert outcome.metrics["payment"] == 70.0
    assert outcome.payoffs["bidder_c"] == -30.0
    underbid = {"bidder_a": 1.0, "bidder_b": 65.0, "bidder_c": 40.0}
    mechanism.validate_actions(config.world, state, bid_actions(underbid))
    lost = mechanism.evaluate(config.world, state, bid_actions(underbid))
    assert lost.metrics["winner"] == "bidder_b"
    assert lost.payoffs["bidder_a"] == 0.0


def test_mechanism_rejects_illegal_actions() -> None:
    mechanism, config, state = mechanism_fixture()
    base = {"bidder_a": 70.0, "bidder_b": 65.0, "bidder_c": 40.0}
    for bad in (-1.0, float("nan"), float("inf"), True, "70", None):
        with pytest.raises(ValueError):
            actions = bid_actions({**base, "bidder_c": bad})  # type: ignore[dict-item]
            mechanism.validate_actions(config.world, state, actions)
    with pytest.raises(ValueError):
        mechanism.validate_actions(config.world, state, bid_actions(base, kind="offer"))
    with pytest.raises(ValueError):
        mechanism.validate_actions(config.world, state, bid_actions(base)[:2])
    renamed = bid_actions(base)
    renamed[0] = renamed[0].model_copy(update={"actor_id": "bidder_x"})
    with pytest.raises(ValueError):
        mechanism.validate_actions(config.world, state, renamed)
    duplicated = [*bid_actions(base), *bid_actions(base)[:1]]
    with pytest.raises(ValueError):
        mechanism.validate_actions(config.world, state, duplicated)


def test_mechanism_reusable_across_valuations() -> None:
    actors = ("x", "y")
    valuations = {"x": 10.0, "y": 7.5}
    mechanism, config, state = mechanism_fixture(actors, valuations)
    bids = {"x": 4.0, "y": 9.0}
    outcome = mechanism.evaluate(config.world, state, bid_actions(bids))
    assert outcome.metrics["winner"] == "y"
    assert outcome.metrics["payment"] == 4.0
    assert outcome.payoffs == {"x": 0.0, "y": 3.5}
    reordered = fixture_config(simulation_dict(actors, valuations, ("y", "x")))
    tied = {"x": 5.0, "y": 5.0}
    outcome = mechanism.evaluate(reordered.world, state, bid_actions(tied))
    assert outcome.metrics["winner"] == "y"
    assert outcome.metrics["payment"] == 5.0


def test_mechanism_records_history_and_state() -> None:
    mechanism, config, state = mechanism_fixture()
    bids = {"bidder_a": 70.0, "bidder_b": 65.0, "bidder_c": 40.0}
    result = mechanism.transition(config.world, state, bid_actions(bids))
    assert result.public["bids"] == [bids]
    assert result.public["winner"] == "bidder_a"
    assert result.public["payment"] == 65.0
    assert result.public["payoffs"] == {"bidder_a": 25.0, "bidder_b": 0.0, "bidder_c": 0.0}
    assert result.outcome.payoffs["bidder_a"] == 25.0
    assert result.private_updates == {}
    progressed = state.model_copy(update={"tick": 1, "phase": "finished", "public": result.public})
    mechanism.validate_state(config.world, progressed)
    tampered = state.model_copy(
        update={
            "tick": 1,
            "phase": "finished",
            "public": {**result.public, "payment": 1.0},
        }
    )
    with pytest.raises(ValueError):
        mechanism.validate_state(config.world, tampered)


def test_mechanism_config_enforces_sealed_observations() -> None:
    mechanism, config, state = mechanism_fixture()
    actors = {actor.id: actor for actor in config.world.actors}
    for actor_id in ACTORS:
        permissions = permissions_for(config, actor_id, "act")
        assert set(permissions.public_fields) == {"rules"}
        observation = observe(actors[actor_id], state, permissions)
        assert set(observation.visible) == {"rules"}
        assert observation.private.facts == {"valuation": VALUATIONS[actor_id]}
        dumped = observation.model_dump_json()
        for other, value in VALUATIONS.items():
            if other != actor_id:
                assert str(value) not in dumped
    assert mechanism.requires_joint_actions is True
