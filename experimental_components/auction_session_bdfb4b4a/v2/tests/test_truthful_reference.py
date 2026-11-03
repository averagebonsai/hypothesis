"""Acceptance tests for the truthful-bidding reference calculation."""

import pytest
from experiment_extension.auction import TruthfulReference, truthful_reference

ORDER = ("bidder_a", "bidder_b", "bidder_c")


def _oracle_payoff(bids, order, valuations):
    ranked = sorted(order, key=lambda actor: (-bids[actor], order.index(actor)))
    payment = sorted(bids.values(), reverse=True)[1]
    winner = ranked[0]
    return {
        actor: (valuations[actor] - payment if actor == winner else 0.0) for actor in order
    }, payment


def test_truthful_reference_main():
    valuations = {"bidder_a": 90.0, "bidder_b": 65.0, "bidder_c": 40.0}
    reference = truthful_reference(valuations, ORDER)
    assert isinstance(reference, TruthfulReference)
    assert reference.bids == valuations
    assert reference.winner == "bidder_a"
    assert reference.payment == 65.0
    assert reference.payoffs == {"bidder_a": 25.0, "bidder_b": 0.0, "bidder_c": 0.0}


def test_truthful_reference_tie():
    valuations = {"bidder_a": 50.0, "bidder_b": 50.0, "bidder_c": 30.0}
    reference = truthful_reference(valuations, ORDER)
    assert reference.bids == valuations
    assert reference.winner == "bidder_a"
    assert reference.payment == 50.0
    assert reference.payoffs == {"bidder_a": 0.0, "bidder_b": 0.0, "bidder_c": 0.0}


def test_truthful_weakly_dominant_sampled():
    valuations = {"bidder_a": 90.0, "bidder_b": 65.0, "bidder_c": 40.0}
    reference = truthful_reference(valuations, ORDER)
    assert reference.payoffs["bidder_a"] == 25.0
    expected = {
        0.0: 0.0,
        20.0: 0.0,
        40.0: 0.0,
        64.0: 0.0,
        65.0: 25.0,
        66.0: 25.0,
        90.0: 25.0,
        120.0: 25.0,
        200.0: 25.0,
    }
    for deviation, payoff in expected.items():
        bids = {"bidder_a": deviation, "bidder_b": 65.0, "bidder_c": 40.0}
        payoffs, _ = _oracle_payoff(bids, ORDER, valuations)
        assert payoffs["bidder_a"] == payoff
        assert payoffs["bidder_a"] <= reference.payoffs["bidder_a"]


def test_truthful_reference_rejects_single_bidder():
    with pytest.raises(ValueError):
        truthful_reference({"bidder_a": 90.0}, ("bidder_a",))
    with pytest.raises(ValueError):
        truthful_reference({"bidder_a": 90.0, "bidder_b": 65.0}, ("bidder_a", "bidder_c"))
