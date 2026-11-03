"""Acceptance tests for the sealed-bid second-price auction mechanism and schemas."""

import pytest
from experiment_extension.auction import (
    AuctionParameters,
    BidPayload,
    SecondPriceAuctionMechanism,
)

from agent_tools.fixtures import fixture_config, fixture_state
from components.library import standard_registry
from components.protocols.simultaneous import SimultaneousProtocol
from simulation_core.observation import observe, permissions_for
from simulation_core.runtime import SimulationRuntime
from simulation_core.types import Action

MECHANISM_ID = "experimental.auction_session_bdfb4b4a.second_price_auction"
BID_SCHEMA_ID = "experimental.auction_session_bdfb4b4a.bid_payload"

VALUATIONS = {"bidder_a": 90.0, "bidder_b": 65.0, "bidder_c": 40.0}


def _simulation_dict(bids=None):
    bids = bids or {"bidder_a": 80.0, "bidder_b": 70.0, "bidder_c": 30.0}
    actors = [
        {
            "id": actor_id,
            "kind": "bidder",
            "action_space": {"schemas": {"submit_bid": BID_SCHEMA_ID}},
            "policy_id": "scripted.v1",
            "policy_parameters": {"kind": "submit_bid", "payload": {"bid": bid}},
        }
        for actor_id, bid in bids.items()
    ]
    return {
        "world": {
            "actors": actors,
            "parameters": {
                "action_kind": "submit_bid",
                "valuation_field": "valuation",
                "rules_field": "auction_rules",
                "history_field": "bid_history",
                "outcome_field": "auction_outcome",
                "value_model": "independent_private_values",
                "utility_model": "quasi_linear",
                "reserve_price": 0.0,
                "budget_constraints": "none",
                "tie_break": "configuration_order",
            },
            "initial_public_state": {
                "auction_rules": {
                    "format": "sealed_bid_second_price",
                    "rounds": 1,
                    "bids_per_bidder": 1,
                    "payment": "second_highest_bid",
                    "tie_break": "configuration_order",
                    "reserve_price": 0.0,
                    "item": "one_indivisible_item",
                }
            },
            "initial_private_state": {
                actor_id: {"facts": {"valuation": value}} for actor_id, value in VALUATIONS.items()
            },
        },
        "mechanism_id": MECHANISM_ID,
        "protocol_id": "simultaneous.v1",
        "protocol_parameters": {"rounds": 1},
        "permissions": {
            actor_id: {
                "public_fields": ["auction_rules"],
                "private_fields": ["valuation"],
                "readable_memory": True,
                "writable_private_fields": [],
                "writable_memory": True,
            }
            for actor_id in VALUATIONS
        },
        "max_steps": 5,
    }


def _mechanism_case(bids):
    config = fixture_config(_simulation_dict(bids))
    protocol = SimultaneousProtocol({"rounds": 1})
    return config, fixture_state(config, protocol)


def _actions(bids):
    return [
        Action(actor_id=actor_id, kind="submit_bid", payload={"bid": bid})
        for actor_id, bid in bids.items()
    ]


def test_mechanism_clearing():
    mechanism = SecondPriceAuctionMechanism()
    bids = {"bidder_a": 80.0, "bidder_b": 70.0, "bidder_c": 30.0}
    config, state = _mechanism_case(bids)
    before = state.model_dump(mode="json")
    mechanism.validate_config(config.world)
    mechanism.validate_state(config.world, state)
    actions = _actions(bids)
    mechanism.validate_actions(config.world, state, actions)
    outcome = mechanism.evaluate(config.world, state, actions)
    assert state.model_dump(mode="json") == before
    assert outcome.payoffs == {"bidder_a": 20.0, "bidder_b": 0.0, "bidder_c": 0.0}
    assert outcome.metrics["winner"] == "bidder_a"
    assert outcome.metrics["payment"] == 70.0
    assert outcome.metrics["bids"] == bids
    transition = mechanism.transition(config.world, state, actions)
    assert transition.public["bid_history"] == [bids]
    assert transition.public["auction_outcome"]["winner"] == "bidder_a"
    assert transition.public["auction_outcome"]["payment"] == 70.0
    assert transition.outcome.payoffs == outcome.payoffs


def test_mechanism_tie_break():
    mechanism = SecondPriceAuctionMechanism()
    config, state = _mechanism_case({"bidder_a": 60.0, "bidder_b": 60.0, "bidder_c": 40.0})
    actions = _actions({"bidder_a": 60.0, "bidder_b": 60.0, "bidder_c": 40.0})
    mechanism.validate_actions(config.world, state, actions)
    outcome = mechanism.evaluate(config.world, state, actions)
    assert outcome.metrics["winner"] == "bidder_a"
    assert outcome.metrics["payment"] == 60.0
    assert outcome.payoffs == {"bidder_a": 30.0, "bidder_b": 0.0, "bidder_c": 0.0}
    config, state = _mechanism_case({"bidder_a": 0.0, "bidder_b": 0.0, "bidder_c": 0.0})
    actions = _actions({"bidder_a": 0.0, "bidder_b": 0.0, "bidder_c": 0.0})
    mechanism.validate_actions(config.world, state, actions)
    outcome = mechanism.evaluate(config.world, state, actions)
    assert outcome.metrics["winner"] == "bidder_a"
    assert outcome.metrics["payment"] == 0.0
    assert outcome.payoffs["bidder_a"] == 90.0


def test_mechanism_overbidding_legal():
    mechanism = SecondPriceAuctionMechanism()
    bids = {"bidder_a": 70.0, "bidder_b": 100.0, "bidder_c": 30.0}
    config, state = _mechanism_case(bids)
    actions = _actions(bids)
    mechanism.validate_actions(config.world, state, actions)
    outcome = mechanism.evaluate(config.world, state, actions)
    assert outcome.metrics["winner"] == "bidder_b"
    assert outcome.metrics["payment"] == 70.0
    assert outcome.payoffs["bidder_b"] == pytest.approx(-5.0)
    assert outcome.payoffs["bidder_a"] == 0.0
    assert outcome.payoffs["bidder_c"] == 0.0


def test_mechanism_rejects_negative_bid():
    mechanism = SecondPriceAuctionMechanism()
    bids = {"bidder_a": 80.0, "bidder_b": -1.0, "bidder_c": 30.0}
    config, state = _mechanism_case({"bidder_a": 80.0, "bidder_b": 70.0, "bidder_c": 30.0})
    with pytest.raises(ValueError):
        mechanism.validate_actions(config.world, state, _actions(bids))


def test_mechanism_rejects_nonfinite_bid():
    mechanism = SecondPriceAuctionMechanism()
    config, state = _mechanism_case({"bidder_a": 80.0, "bidder_b": 70.0, "bidder_c": 30.0})
    for bad in (float("inf"), float("nan")):
        actions = _actions({"bidder_a": 80.0, "bidder_b": 70.0, "bidder_c": 30.0})
        actions[1] = Action.model_construct(
            actor_id="bidder_b", kind="submit_bid", payload={"bid": bad}
        )
        with pytest.raises(ValueError):
            mechanism.validate_actions(config.world, state, actions)


def test_mechanism_rejects_wrong_kind():
    mechanism = SecondPriceAuctionMechanism()
    config, state = _mechanism_case({"bidder_a": 80.0, "bidder_b": 70.0, "bidder_c": 30.0})
    actions = _actions({"bidder_a": 80.0, "bidder_b": 70.0, "bidder_c": 30.0})
    actions[0] = Action(actor_id="bidder_a", kind="set_price", payload={"bid": 80.0})
    with pytest.raises(ValueError):
        mechanism.validate_actions(config.world, state, actions)
    with pytest.raises(ValueError):
        mechanism.validate_actions(config.world, state, actions[1:])


def test_mechanism_rejects_unsupported_parameters():
    mechanism = SecondPriceAuctionMechanism()
    payload = _simulation_dict()
    payload["world"]["parameters"]["reserve_price"] = 1.0
    with pytest.raises(ValueError):
        mechanism.validate_config(fixture_config(payload).world)
    payload = _simulation_dict()
    payload["world"]["parameters"]["value_model"] = "common_value"
    with pytest.raises(ValueError):
        mechanism.validate_config(fixture_config(payload).world)
    payload = _simulation_dict()
    payload["world"]["actors"] = payload["world"]["actors"][:1]
    payload["permissions"] = {"bidder_a": payload["permissions"]["bidder_a"]}
    payload["world"]["initial_private_state"] = {
        "bidder_a": payload["world"]["initial_private_state"]["bidder_a"]
    }
    with pytest.raises(ValueError):
        mechanism.validate_config(fixture_config(payload).world)


def test_bid_payload_bounds():
    assert BidPayload(bid=0.0).bid == 0.0
    assert BidPayload(bid=250.5).bid == 250.5
    with pytest.raises(ValueError):
        BidPayload(bid=-0.5)
    with pytest.raises(ValueError):
        BidPayload(bid=float("inf"))
    with pytest.raises(ValueError):
        BidPayload(bid=float("nan"))


def test_auction_parameters_defaults():
    params = AuctionParameters()
    assert params.action_kind == "submit_bid"
    assert params.valuation_field == "valuation"
    assert params.rules_field == "auction_rules"
    assert params.history_field == "bid_history"
    assert params.outcome_field == "auction_outcome"
    assert params.value_model == "independent_private_values"
    assert params.utility_model == "quasi_linear"
    assert params.reserve_price == 0.0
    assert params.budget_constraints == "none"
    assert params.tie_break == "configuration_order"
    base = params.model_dump(mode="json")
    for key, bad in (
        ("value_model", "common_value"),
        ("utility_model", "risk_averse"),
        ("reserve_price", 1.0),
        ("budget_constraints", "tight"),
        ("tie_break", "random"),
    ):
        with pytest.raises(ValueError):
            AuctionParameters.model_validate({**base, key: bad})


def test_sealed_bid_run_offline():
    registry = standard_registry()
    registry.mechanisms[MECHANISM_ID] = SecondPriceAuctionMechanism
    registry.action_schemas[BID_SCHEMA_ID] = BidPayload
    registry.parameter_schemas[MECHANISM_ID] = AuctionParameters
    bids = {"bidder_a": 88.0, "bidder_b": 60.0, "bidder_c": 45.0}
    config = fixture_config(_simulation_dict(bids))
    SecondPriceAuctionMechanism().validate_config(config.world)
    result = SimulationRuntime(registry).run(config)
    assert result.status == "completed"
    assert len(result.outcomes) == 1
    assert result.outcomes[0].payoffs == {
        "bidder_a": 30.0,
        "bidder_b": 0.0,
        "bidder_c": 0.0,
    }
    assert result.outcomes[0].metrics["winner"] == "bidder_a"
    assert result.outcomes[0].metrics["payment"] == 60.0
    assert result.final_state.public["bid_history"] == [bids]
    protocol = SimultaneousProtocol({"rounds": 1})
    state = fixture_state(config, protocol)
    for actor in config.world.actors:
        observation = observe(actor, state, permissions_for(config, actor.id, state.phase))
        assert set(observation.visible) == {"auction_rules"}
        assert observation.private.facts == {"valuation": VALUATIONS[actor.id]}
