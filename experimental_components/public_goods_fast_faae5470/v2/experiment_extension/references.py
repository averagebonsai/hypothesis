"""Closed-form mathematical references for the withdrawal game.

Two benchmarks, both plain arithmetic over the resolved configuration:

* Zero contribution: every actor contributes nothing every round. Under the
  textbook finite-horizon assumptions (risk-neutral own-wealth maximizers with
  common knowledge of the known horizon, via backward induction), this is the
  self-interested benchmark path.
* Full reinvestment: every actor contributes all available funds every round.
  For multiplier > 1 this grows group wealth fastest and serves as a
  cooperative group-wealth reference. It is not a Nash equilibrium.

Neither reference predicts live-actor behavior.
"""

from simulation_core.types import FrozenModel


class ReferencePoint(FrozenModel):
    round: int
    endowment: float
    contribution: float
    payoff: float
    balance: float


def _check(
    participant_count: int,
    rounds: int,
    endowed_rounds: int,
    endowment: float,
    multiplier: float,
) -> None:
    if participant_count < 1:
        raise ValueError("participant_count must be positive")
    if rounds < 1:
        raise ValueError("rounds must be positive")
    if not 0 <= endowed_rounds <= rounds:
        raise ValueError("endowed_rounds must lie within the horizon")
    if endowment < 0.0:
        raise ValueError("endowment cannot be negative")
    if multiplier <= 0.0:
        raise ValueError("multiplier must be positive")


def marginal_private_return(multiplier: float, participant_count: int) -> float:
    """Pool return to the contributor per unit contributed: multiplier / N."""
    if multiplier <= 0.0:
        raise ValueError("multiplier must be positive")
    if participant_count < 1:
        raise ValueError("participant_count must be positive")
    return multiplier / participant_count


def zero_contribution_trajectory(
    participant_count: int,
    rounds: int,
    endowed_rounds: int,
    endowment: float,
    multiplier: float,
) -> tuple[ReferencePoint, ...]:
    _check(participant_count, rounds, endowed_rounds, endowment, multiplier)
    balance = 0.0
    path = []
    for round_no in range(1, rounds + 1):
        grant = endowment if round_no <= endowed_rounds else 0.0
        balance += grant
        path.append(
            ReferencePoint(
                round=round_no,
                endowment=grant,
                contribution=0.0,
                payoff=grant,
                balance=balance,
            )
        )
    return tuple(path)


def full_reinvestment_trajectory(
    participant_count: int,
    rounds: int,
    endowed_rounds: int,
    endowment: float,
    multiplier: float,
) -> tuple[ReferencePoint, ...]:
    _check(participant_count, rounds, endowed_rounds, endowment, multiplier)
    balance = 0.0
    path = []
    for round_no in range(1, rounds + 1):
        grant = endowment if round_no <= endowed_rounds else 0.0
        available = balance + grant
        closing = multiplier * available
        path.append(
            ReferencePoint(
                round=round_no,
                endowment=grant,
                contribution=available,
                payoff=closing - balance,
                balance=closing,
            )
        )
        balance = closing
    return tuple(path)


def reference_trajectories(
    participant_count: int,
    rounds: int,
    endowed_rounds: int,
    endowment: float,
    multiplier: float,
) -> dict[str, tuple[ReferencePoint, ...]]:
    return {
        "zero_contribution": zero_contribution_trajectory(
            participant_count, rounds, endowed_rounds, endowment, multiplier
        ),
        "full_reinvestment": full_reinvestment_trajectory(
            participant_count, rounds, endowed_rounds, endowment, multiplier
        ),
    }
