"""Mathematical references: closed-form trajectories with hand-derived values.

Zero-contribution path (request values N=3, m=2, e=20, rounds=6, endowed=3):
each actor keeps every endowment, ending at 60.
Full-reinvestment path with all actors contributing all available funds each round:
closing balance equals m times available funds, ending at 2240 per actor.
"""

import pytest
from experiment_extension.references import (
    full_reinvestment_trajectory,
    marginal_private_return,
    reference_trajectories,
    zero_contribution_trajectory,
)


def test_marginal_private_return_request_values():
    assert marginal_private_return(2.0, 3) == pytest.approx(2.0 / 3.0)


def test_marginal_private_return_rejects_bad_inputs():
    with pytest.raises((ValueError, TypeError)):
        marginal_private_return(0.0, 3)
    with pytest.raises((ValueError, TypeError)):
        marginal_private_return(2.0, 0)


def test_zero_trajectory_request_values():
    path = zero_contribution_trajectory(
        participant_count=3,
        rounds=6,
        endowed_rounds=3,
        endowment=20.0,
        multiplier=2.0,
    )
    assert [p.round for p in path] == [1, 2, 3, 4, 5, 6]
    assert [p.endowment for p in path] == [20.0, 20.0, 20.0, 0.0, 0.0, 0.0]
    assert [p.contribution for p in path] == [0.0] * 6
    assert [p.payoff for p in path] == [20.0, 20.0, 20.0, 0.0, 0.0, 0.0]
    assert [p.balance for p in path] == [20.0, 40.0, 60.0, 60.0, 60.0, 60.0]


def test_full_reinvestment_trajectory_request_values():
    path = full_reinvestment_trajectory(
        participant_count=3,
        rounds=6,
        endowed_rounds=3,
        endowment=20.0,
        multiplier=2.0,
    )
    # Available funds each round: 20, 60, 140, 280, 560, 1120; closing = 2x available.
    assert [p.contribution for p in path] == [20.0, 60.0, 140.0, 280.0, 560.0, 1120.0]
    assert [p.payoff for p in path] == [40.0, 80.0, 160.0, 280.0, 560.0, 1120.0]
    assert [p.balance for p in path] == [40.0, 120.0, 280.0, 560.0, 1120.0, 2240.0]


def test_full_reinvestment_varied_parameters():
    # N=2, m=1.5, e=10, rounds=2, endowed=1: r1 avail 10 -> 15; r2 avail 15 -> 22.5.
    path = full_reinvestment_trajectory(
        participant_count=2,
        rounds=2,
        endowed_rounds=1,
        endowment=10.0,
        multiplier=1.5,
    )
    assert [p.contribution for p in path] == [10.0, 15.0]
    assert [p.payoff for p in path] == [15.0, 7.5]
    assert [p.balance for p in path] == [15.0, 22.5]


def test_zero_trajectory_without_endowments():
    path = zero_contribution_trajectory(
        participant_count=4,
        rounds=3,
        endowed_rounds=0,
        endowment=20.0,
        multiplier=2.0,
    )
    assert [p.balance for p in path] == [0.0, 0.0, 0.0]


def test_trajectories_reject_bad_parameters():
    with pytest.raises((ValueError, TypeError)):
        zero_contribution_trajectory(
            participant_count=3,
            rounds=6,
            endowed_rounds=7,
            endowment=20.0,
            multiplier=2.0,
        )
    with pytest.raises((ValueError, TypeError)):
        full_reinvestment_trajectory(
            participant_count=3,
            rounds=0,
            endowed_rounds=0,
            endowment=20.0,
            multiplier=2.0,
        )
    with pytest.raises((ValueError, TypeError)):
        full_reinvestment_trajectory(
            participant_count=3,
            rounds=6,
            endowed_rounds=3,
            endowment=-1.0,
            multiplier=2.0,
        )
    with pytest.raises((ValueError, TypeError)):
        zero_contribution_trajectory(
            participant_count=3,
            rounds=6,
            endowed_rounds=3,
            endowment=20.0,
            multiplier=0.0,
        )


def test_reference_trajectories_closed_form():
    bundle = reference_trajectories(
        participant_count=3,
        rounds=6,
        endowed_rounds=3,
        endowment=20.0,
        multiplier=2.0,
    )
    assert set(bundle) == {"zero_contribution", "full_reinvestment"}
    assert bundle["zero_contribution"][-1].balance == 60.0
    assert bundle["full_reinvestment"][-1].balance == 2240.0
    assert marginal_private_return(2.0, 3) == pytest.approx(2.0 / 3.0)


def test_one_shot_deviation_gain_formula():
    # Withholding c instead of contributing it gains c * (1 - m/N) in one round:
    # N=3, m=2, contributions (10, 20, 0): p1 earns 30, but 0 would earn 100/3.
    gain = 100.0 / 3.0 - 30.0
    keep_rate = 1.0 - marginal_private_return(2.0, 3)
    assert gain == pytest.approx(10.0 * keep_rate)
    # The scope is one round only; the finite-horizon zero path additionally
    # assumes backward induction under common knowledge of the known horizon.
