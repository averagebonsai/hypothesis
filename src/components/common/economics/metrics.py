"""Economic, welfare, and strategic diagnostics."""

from collections.abc import Mapping, Sequence
from math import isfinite


def gini_coefficient(values: Sequence[float]) -> float:
    """Compute Gini inequality coefficient for non-negative values.

    Returns 0.0 for perfect equality, approaching 1.0 for extreme inequality.
    """
    if not values:
        return 0.0
    for v in values:
        if not isfinite(v) or v < 0:
            raise ValueError("Gini coefficient requires finite, non-negative values")

    sorted_vals = sorted(values)
    n = len(sorted_vals)
    total = sum(sorted_vals)
    if total == 0.0:
        return 0.0

    # Formula: G = (2 * sum(i * y_i) / (n * sum(y))) - (n + 1) / n
    weighted_sum = sum((i + 1) * val for i, val in enumerate(sorted_vals))
    return float((2.0 * weighted_sum) / (n * total) - (n + 1.0) / n)


def herfindahl_index(market_shares: Mapping[str, float]) -> float:
    """Compute Herfindahl-Hirschman Index (HHI) given proportional market shares (summing to 1.0).

    Returns value between 0 and 10,000.
    """
    if not market_shares:
        return 0.0
    for share in market_shares.values():
        if not isfinite(share) or share < 0:
            raise ValueError("Market shares must be finite non-negative numbers")

    total_share = sum(market_shares.values())
    if abs(total_share - 1.0) > 1e-4:
        raise ValueError(f"Market shares must sum to 1.0, got {total_share}")

    return float(sum((share * 100.0) ** 2 for share in market_shares.values()))


def social_welfare(payoffs: Mapping[str, float]) -> float:
    """Compute total utilitarian social welfare (sum of individual payoffs)."""
    for p in payoffs.values():
        if not isfinite(p):
            raise ValueError("Payoffs must be finite")
    return float(sum(payoffs.values()))


def unilateral_regret(
    actual_payoff: float, counterfactual_best_payoff: float
) -> float:
    """Compute unilateral deviation regret (gain from deviation)."""
    if not (isfinite(actual_payoff) and isfinite(counterfactual_best_payoff)):
        raise ValueError("Payoffs must be finite")
    return max(0.0, counterfactual_best_payoff - actual_payoff)


def economic_efficiency(actual_surplus: float, theoretical_max_surplus: float) -> float:
    """Compute realized economic efficiency as a fraction of theoretical maximum surplus."""
    if not (isfinite(actual_surplus) and isfinite(theoretical_max_surplus)):
        raise ValueError("Surplus values must be finite")
    if theoretical_max_surplus <= 0:
        return 1.0 if actual_surplus >= theoretical_max_surplus else 0.0
    return float(max(0.0, min(1.0, actual_surplus / theoretical_max_surplus)))
