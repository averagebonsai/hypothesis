"""Acceptance tests for the sealed-bid payload schema."""

import pytest
from experiment_extension.auction import BidPayload
from pydantic import ValidationError


def test_bid_schema_accepts_finite_nonnegative() -> None:
    assert BidPayload.model_validate({"bid": 65.0}).bid == 65.0
    assert BidPayload.model_validate({"bid": 0.0}).bid == 0.0
    assert BidPayload.model_validate({"bid": 90}).bid == 90.0
    assert BidPayload.model_validate({"bid": 250000.125}).bid == 250000.125


def test_bid_schema_rejects_invalid_bids() -> None:
    for payload in (
        {"bid": -1.0},
        {"bid": -0.5},
        {"bid": float("nan")},
        {"bid": float("inf")},
        {"bid": float("-inf")},
        {"bid": True},
        {"bid": "65"},
        {"bid": None},
        {"bid": [65.0]},
        {"offer": 65.0},
        {},
    ):
        with pytest.raises(ValidationError):
            BidPayload.model_validate(payload)


def test_bid_schema_preserves_exact_amount() -> None:
    assert BidPayload.model_validate({"bid": 65.25}).bid == 65.25
    assert BidPayload.model_validate({"bid": 0.125}).bid == 0.125
    assert BidPayload.model_validate({"bid": 1000000.0}).bid == 1000000.0
