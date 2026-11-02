"""Acceptance tests for auction parameters and the truthful reference utility."""

import pytest
from auction_fixtures import VALUATIONS, world_parameters
from experiment_extension.auction import AuctionParameters, truthful_reference
from pydantic import ValidationError


def test_truthful_reference_matches_valuations() -> None:
    reference = truthful_reference(dict(VALUATIONS), ["bidder_a", "bidder_b", "bidder_c"])
    assert reference.bids == {"bidder_a": 90.0, "bidder_b": 65.0, "bidder_c": 40.0}
    assert reference.winner == "bidder_a"
    assert reference.payment == 65.0
    assert reference.utilities == {"bidder_a": 25.0, "bidder_b": 0.0, "bidder_c": 0.0}


def test_truthful_reference_breaks_ties_by_order() -> None:
    valuations = {"a": 50.0, "b": 50.0, "c": 10.0}
    first = truthful_reference(valuations, ["a", "b", "c"])
    assert first.winner == "a"
    assert first.payment == 50.0
    assert first.utilities == {"a": 0.0, "b": 0.0, "c": 0.0}
    second = truthful_reference(valuations, ("b", "a", "c"))
    assert second.winner == "b"
    assert second.payment == 50.0
    assert second.utilities["b"] == 0.0
    assert second.bids == valuations


def test_truthful_reference_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        truthful_reference({}, [])
    with pytest.raises(ValueError):
        truthful_reference({"a": 10.0}, [])
    with pytest.raises(ValueError):
        truthful_reference({"a": 10.0, "b": 5.0}, ["a"])
    with pytest.raises(ValueError):
        truthful_reference({"a": 10.0}, ["a", "b"])
    with pytest.raises(ValueError):
        truthful_reference({"a": 10.0, "b": 5.0}, ["a", "a"])
    with pytest.raises(ValueError):
        truthful_reference({"a": -1.0, "b": 5.0}, ["a", "b"])
    with pytest.raises(ValueError):
        truthful_reference({"a": float("nan"), "b": 5.0}, ["a", "b"])
    with pytest.raises(ValueError):
        truthful_reference({"a": float("inf"), "b": 5.0}, ["a", "b"])
    with pytest.raises((ValueError, ValidationError, TypeError)):
        truthful_reference({"a": "10", "b": 5.0}, ["a", "b"])


def test_auction_params_accepts_reusable_config() -> None:
    full = AuctionParameters.from_json_values(world_parameters())
    assert full.action_kind == "bid"
    assert full.tie_break_order == ("bidder_a", "bidder_b", "bidder_c")
    assert full.pricing == "second_price"
    assert full.reserve == 0.0
    minimal = AuctionParameters.from_json_values({"tie_break_order": ["x", "y"]})
    assert minimal.tie_break_order == ("x", "y")
    assert minimal.action_kind == "bid"
    assert minimal.valuation_fact == "valuation"
    assert minimal.bids_field == "bids"
    assert minimal.allow_above_valuation is True


def test_auction_params_rejects_bad_config() -> None:
    base = world_parameters()
    for override in (
        {"tie_break_order": ["a", "a"]},
        {"tie_break_order": ["a"]},
        {"tie_break_order": []},
        {"tie_break_order": ["a", ""]},
        {"pricing": "first_price"},
        {"values_model": "common_values"},
        {"utility_model": "risk_averse"},
        {"item": "divisible"},
        {"reserve": 5.0},
        {"budgets": "limited"},
        {"bids_field": "winner"},
        {"winner_field": "payment"},
        {"action_kind": ""},
    ):
        with pytest.raises(ValidationError):
            AuctionParameters.from_json_values({**base, **override})
