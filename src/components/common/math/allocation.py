"""Mathematical allocation and optimization routines."""

from collections.abc import Mapping, Sequence
from math import isfinite

from pydantic import Field
from scipy.optimize import linear_sum_assignment, linprog

from simulation_core.types import FrozenModel


class LPResult(FrozenModel):
    """Result of linear program optimization."""

    status: str
    success: bool
    x: tuple[float, ...] = Field(default_factory=tuple)  # type: ignore[assignment]
    fun: float | None = None


def proportional_rationing(
    demands: Mapping[str, float], total_capacity: float
) -> dict[str, float]:
    """Allocate capacity proportionally to demands when capacity is constrained.

    Guarantees that allocated amounts sum to at most total_capacity,
    and each actor receives at most their requested demand.
    """
    if not isfinite(total_capacity) or total_capacity < 0:
        raise ValueError("Capacity must be finite and non-negative")
    for aid, demand in demands.items():
        if not isfinite(demand) or demand < 0:
            raise ValueError(f"Demand for {aid} must be finite and non-negative")

    total_demand = sum(demands.values())
    if total_demand <= total_capacity or total_demand == 0.0:
        return {aid: demand for aid, demand in demands.items()}

    # Scale down by ratio
    ratio = total_capacity / total_demand
    allocated = {aid: demand * ratio for aid, demand in demands.items()}

    # Adjust rounding discrepancy on largest demand to guarantee exact conservation
    diff = total_capacity - sum(allocated.values())
    if abs(diff) > 0 and allocated:
        max_id = max(allocated, key=allocated.get)  # type: ignore[arg-type]
        allocated[max_id] += diff

    return allocated


def priority_rationing(
    demands: Mapping[str, float],
    priorities: Mapping[str, float],
    total_capacity: float,
) -> dict[str, float]:
    """Allocate capacity strictly in descending order of priority."""
    if not isfinite(total_capacity) or total_capacity < 0:
        raise ValueError("Capacity must be finite and non-negative")
    for aid in demands:
        if aid not in priorities:
            raise ValueError(f"Missing priority for {aid}")

    sorted_actors = sorted(demands.keys(), key=lambda a: priorities[a], reverse=True)
    allocated: dict[str, float] = {}
    remaining = total_capacity

    for aid in sorted_actors:
        needed = demands[aid]
        grant = min(needed, remaining)
        allocated[aid] = grant
        remaining -= grant

    return allocated


def solve_linear_program(
    c: Sequence[float],
    *,
    a_ub: Sequence[Sequence[float]] | None = None,
    b_ub: Sequence[float] | None = None,
    a_eq: Sequence[Sequence[float]] | None = None,
    b_eq: Sequence[float] | None = None,
    bounds: Sequence[tuple[float | None, float | None]] | None = None,
) -> LPResult:
    """Solve min c^T x subject to A_ub x <= b_ub and A_eq x == b_eq."""
    result = linprog(  # type: ignore[call-overload,misc]
        c=c,
        A_ub=a_ub,
        b_ub=b_ub,
        A_eq=a_eq,
        b_eq=b_eq,
        bounds=bounds,
        method="highs",
    )
    return LPResult(
        status=result.message,
        success=bool(result.success),
        x=tuple(float(v) for v in result.x) if result.x is not None else (),
        fun=float(result.fun) if result.fun is not None else None,
    )


def optimal_bipartite_matching(
    cost_matrix: Sequence[Sequence[float]], *, maximize: bool = False
) -> tuple[tuple[int, int], ...]:
    """Compute optimal 1-to-1 matching between two sets using the Hungarian algorithm."""
    row_ind, col_ind = linear_sum_assignment(cost_matrix, maximize=maximize)
    return tuple(zip((int(r) for r in row_ind), (int(c) for c in col_ind), strict=True))
