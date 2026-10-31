"""Reusable bounded one-dimensional objective search, with explicit numerical limits."""

from collections.abc import Callable
from math import isfinite

import numpy as np
from numpy.typing import NDArray
from pydantic import Field
from scipy.optimize import minimize_scalar, shgo

from simulation_core.types import FrozenModel


class OptimizationBudgetExceeded(ArithmeticError):
    pass


class ScalarSearchSettings(FrozenModel):
    grid_points: int = Field(default=65, ge=9, le=513)
    max_evaluations: int = Field(default=3000, gt=0, le=50000)
    price_tolerance: float = Field(default=1e-8, gt=0)


class ScalarMaximum(FrozenModel):
    value: float
    payoff: float
    evaluations: int
    method: str
    optimizer_successes: int


def maximize_scalar(
    objective: Callable[[float], float],
    bounds: tuple[float, float],
    settings: ScalarSearchSettings,
    current: float,
    independent: bool = False,
) -> ScalarMaximum:
    low, high = bounds
    if not isfinite(low) or not isfinite(high) or not low < high:
        raise ValueError("Scalar search requires ordered finite bounds")
    calls = 0
    cache: dict[float, float] = {}

    def evaluate(value: float) -> float:
        nonlocal calls
        value = float(np.clip(value, low, high))
        if value not in cache:
            if calls >= settings.max_evaluations:
                raise OptimizationBudgetExceeded("Scalar objective evaluation budget exhausted")
            calls += 1
            payoff = float(objective(value))
            if not isfinite(payoff):
                raise ArithmeticError("Nonfinite scalar payoff")
            cache[value] = payoff
        return cache[value]

    offsets = (high - low) * np.geomspace(1e-12, 1.0, settings.grid_points)
    grid = sorted(
        {float(p) for p in np.linspace(low, high, settings.grid_points)}
        | {float(low + offset) for offset in offsets}
        | {float(high - offset) for offset in offsets}
    )
    values = [evaluate(p) for p in grid]
    evaluate(current)
    successes = 0
    if independent:

        def negative(values: NDArray[np.float64]) -> float:
            return -evaluate(float(values[0]))

        result = shgo(
            negative,
            [(low, high)],
            n=max(128, settings.grid_points),
            iters=2,
            sampling_method="sobol",
            minimizer_kwargs={"method": "L-BFGS-B", "options": {"maxiter": 200, "ftol": 1e-12}},
        )
        if result.success:
            evaluate(float(result.x[0]))
            successes += 1
    else:
        # Refine all sampled peaks, rather than assuming a mixture's profit is unimodal.
        intervals = [
            (grid[i - 1], grid[i + 1])
            for i in range(1, len(grid) - 1)
            if values[i] >= values[i - 1]
            and values[i] >= values[i + 1]
            and (values[i] > values[i - 1] or values[i] > values[i + 1])
        ]
        if not intervals:
            intervals = [(low, high)]
        for interval in intervals:
            local_result = minimize_scalar(
                lambda p: -evaluate(float(p)),
                bounds=interval,
                method="bounded",
                options={"xatol": settings.price_tolerance, "maxiter": 200},
            )
            if local_result.success:
                evaluate(float(local_result.x))
                successes += 1
    if not successes and max(values) - min(values) > 1e-10:
        raise ArithmeticError("Scalar optimizer did not converge")
    best = max(cache, key=cache.__getitem__)
    return ScalarMaximum(
        value=best,
        payoff=cache[best],
        evaluations=calls,
        optimizer_successes=successes,
        method="SHGO+uniform-geometric-samples"
        if independent
        else "uniform-geometric-grid+bounded-peaks",
    )
