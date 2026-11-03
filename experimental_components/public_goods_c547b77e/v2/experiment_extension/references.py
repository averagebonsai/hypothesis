"""Closed-form references for the public-goods withdrawal experiment.

These are plain arithmetic utilities, not solver searches: the marginal private
return of one contributed unit, the all-zero trajectory used as the
self-interested reference for the known finite-horizon textbook setting, and the
full-reinvestment trajectory used as the cooperative group-wealth reference when
the multiplier exceeds 1. Scope conditions live with the callers' theory text;
the functions validate their numeric domain and compute the trajectories.
"""

from math import isfinite
from typing import TypedDict


class RoundReference(TypedDict):
    round: int
    endowment_this_round: float
    contribution: float
    per_capita_payout: float
    round_payoff: float
    closing_balance: float


class TrajectoryReference(TypedDict):
    per_round: list[RoundReference]
    final_balance_per_participant: float
    final_group_wealth: float


def _check_count(name: str, value: int, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")  # noqa: TRY004
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _check_amount(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")  # noqa: TRY004
    if not isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return float(value)


def _check_schedule(rounds: int, endowed_rounds: int) -> None:
    if endowed_rounds > rounds:
        raise ValueError("endowed_rounds cannot exceed rounds")


def marginal_private_return(multiplier: float, participant_count: int) -> float:
    """Return the one-round private return of a contributed unit (multiplier/N)."""
    mult = _check_amount("multiplier", multiplier)
    count = _check_count("participant_count", participant_count, 1)
    return mult / count


def zero_contribution_trajectory(
    rounds: int,
    endowed_rounds: int,
    endowment: float,
    participant_count: int,
) -> TrajectoryReference:
    """Trace savings when every participant contributes zero every round."""
    total_rounds = _check_count("rounds", rounds, 1)
    endowed = _check_count("endowed_rounds", endowed_rounds, 0)
    _check_schedule(total_rounds, endowed)
    gift = _check_amount("endowment", endowment)
    count = _check_count("participant_count", participant_count, 1)
    per_round: list[RoundReference] = []
    balance = 0.0
    for number in range(1, total_rounds + 1):
        grant = gift if number <= endowed else 0.0
        balance += grant
        per_round.append(
            {
                "round": number,
                "endowment_this_round": grant,
                "contribution": 0.0,
                "per_capita_payout": 0.0,
                "round_payoff": grant,
                "closing_balance": balance,
            }
        )
    return {
        "per_round": per_round,
        "final_balance_per_participant": balance,
        "final_group_wealth": balance * count,
    }


def full_reinvestment_trajectory(
    rounds: int,
    endowed_rounds: int,
    endowment: float,
    multiplier: float,
    participant_count: int,
) -> TrajectoryReference:
    """Trace savings when everyone contributes all available funds every round."""
    total_rounds = _check_count("rounds", rounds, 1)
    endowed = _check_count("endowed_rounds", endowed_rounds, 0)
    _check_schedule(total_rounds, endowed)
    gift = _check_amount("endowment", endowment)
    mult = _check_amount("multiplier", multiplier)
    count = _check_count("participant_count", participant_count, 1)
    per_round: list[RoundReference] = []
    balance = 0.0
    for number in range(1, total_rounds + 1):
        grant = gift if number <= endowed else 0.0
        available = balance + grant
        payout = mult * (count * available) / count
        payoff = grant - available + payout
        balance += payoff
        per_round.append(
            {
                "round": number,
                "endowment_this_round": grant,
                "contribution": available,
                "per_capita_payout": payout,
                "round_payoff": payoff,
                "closing_balance": balance,
            }
        )
    return {
        "per_round": per_round,
        "final_balance_per_participant": balance,
        "final_group_wealth": balance * count,
    }
