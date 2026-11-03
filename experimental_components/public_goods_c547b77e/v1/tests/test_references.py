"""Acceptance tests for the closed-form public-goods reference utilities."""

import math

import pytest
from experiment_extension.references import (
    full_reinvestment_trajectory,
    marginal_private_return,
    zero_contribution_trajectory,
)


def test_marginal_private_return_value():
    assert math.isclose(marginal_private_return(2.0, 5), 0.4, rel_tol=1e-12)
    assert math.isclose(marginal_private_return(3.0, 4), 0.75, rel_tol=1e-12)
    assert math.isclose(marginal_private_return(1.0, 2), 0.5, rel_tol=1e-12)


def test_marginal_private_return_rejects_bad_inputs():
    for bad_n in (0, -2, True, 2.5, "5"):
        with pytest.raises(ValueError):
            marginal_private_return(2.0, bad_n)
    for bad_mult in (-1.0, float("inf"), float("nan"), "2"):
        with pytest.raises(ValueError):
            marginal_private_return(bad_mult, 5)


def test_zero_trajectory_hand_values():
    result = zero_contribution_trajectory(
        rounds=10, endowed_rounds=5, endowment=20.0, participant_count=5
    )
    assert set(result) == {
        "per_round",
        "final_balance_per_participant",
        "final_group_wealth",
    }
    assert len(result["per_round"]) == 10
    for index, entry in enumerate(result["per_round"], start=1):
        assert set(entry) == {
            "round",
            "endowment_this_round",
            "contribution",
            "per_capita_payout",
            "round_payoff",
            "closing_balance",
        }
        assert entry["round"] == index
        if index <= 5:
            assert entry["endowment_this_round"] == 20.0
            assert entry["round_payoff"] == 20.0
            assert entry["closing_balance"] == 20.0 * index
        else:
            assert entry["endowment_this_round"] == 0.0
            assert entry["round_payoff"] == 0.0
            assert entry["closing_balance"] == 100.0
        assert entry["contribution"] == 0.0
        assert entry["per_capita_payout"] == 0.0
    assert result["final_balance_per_participant"] == 100.0
    assert result["final_group_wealth"] == 500.0


def test_zero_trajectory_varied_params():
    result = zero_contribution_trajectory(
        rounds=4, endowed_rounds=2, endowment=10.0, participant_count=3
    )
    closings = [entry["closing_balance"] for entry in result["per_round"]]
    assert closings == [10.0, 20.0, 20.0, 20.0]
    assert result["final_balance_per_participant"] == 20.0
    assert result["final_group_wealth"] == 60.0
    empty = zero_contribution_trajectory(
        rounds=3, endowed_rounds=0, endowment=10.0, participant_count=3
    )
    assert empty["final_balance_per_participant"] == 0.0
    assert empty["final_group_wealth"] == 0.0


def test_full_reinvestment_hand_values():
    result = full_reinvestment_trajectory(
        rounds=10, endowed_rounds=5, endowment=20.0, multiplier=2.0, participant_count=5
    )
    expected = [
        # (round, endowment, contribution, payout, payoff, closing)
        (1, 20.0, 20.0, 40.0, 40.0, 40.0),
        (2, 20.0, 60.0, 120.0, 80.0, 120.0),
        (3, 20.0, 140.0, 280.0, 160.0, 280.0),
        (4, 20.0, 300.0, 600.0, 320.0, 600.0),
        (5, 20.0, 620.0, 1240.0, 640.0, 1240.0),
        (6, 0.0, 1240.0, 2480.0, 1240.0, 2480.0),
        (7, 0.0, 2480.0, 4960.0, 2480.0, 4960.0),
        (8, 0.0, 4960.0, 9920.0, 4960.0, 9920.0),
        (9, 0.0, 9920.0, 19840.0, 9920.0, 19840.0),
        (10, 0.0, 19840.0, 39680.0, 19840.0, 39680.0),
    ]
    assert len(result["per_round"]) == 10
    for entry, want in zip(result["per_round"], expected):
        assert entry["round"] == want[0]
        assert entry["endowment_this_round"] == want[1]
        assert entry["contribution"] == want[2]
        assert entry["per_capita_payout"] == want[3]
        assert entry["round_payoff"] == want[4]
        assert entry["closing_balance"] == want[5]
    assert result["final_balance_per_participant"] == 39680.0
    assert result["final_group_wealth"] == 198400.0


def test_full_reinvestment_neutral_multiplier():
    result = full_reinvestment_trajectory(
        rounds=3, endowed_rounds=2, endowment=10.0, multiplier=1.0, participant_count=4
    )
    closings = [entry["closing_balance"] for entry in result["per_round"]]
    assert closings == [10.0, 20.0, 20.0]
    # With multiplier 1 there is no wealth creation: final savings equal gifts received.
    assert result["final_balance_per_participant"] == 20.0
    assert result["final_group_wealth"] == 80.0


def test_full_reinvestment_rejects_bad_inputs():
    with pytest.raises(ValueError):
        full_reinvestment_trajectory(
            rounds=0, endowed_rounds=0, endowment=10.0, multiplier=2.0, participant_count=5
        )
    with pytest.raises(ValueError):
        full_reinvestment_trajectory(
            rounds=4, endowed_rounds=5, endowment=10.0, multiplier=2.0, participant_count=5
        )
    with pytest.raises(ValueError):
        full_reinvestment_trajectory(
            rounds=4, endowed_rounds=2, endowment=-1.0, multiplier=2.0, participant_count=5
        )
    with pytest.raises(ValueError):
        full_reinvestment_trajectory(
            rounds=4, endowed_rounds=2, endowment=10.0, multiplier=-0.5, participant_count=5
        )
    with pytest.raises(ValueError):
        full_reinvestment_trajectory(
            rounds=4, endowed_rounds=2, endowment=10.0, multiplier=2.0, participant_count=0
        )
    with pytest.raises(ValueError):
        full_reinvestment_trajectory(
            rounds=4,
            endowed_rounds=2,
            endowment=float("nan"),
            multiplier=2.0,
            participant_count=5,
        )
    with pytest.raises(ValueError):
        zero_contribution_trajectory(
            rounds=4, endowed_rounds=5, endowment=10.0, participant_count=3
        )
    with pytest.raises(ValueError):
        zero_contribution_trajectory(
            rounds=True, endowed_rounds=0, endowment=10.0, participant_count=3
        )
