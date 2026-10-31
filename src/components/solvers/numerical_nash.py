"""Multistart bounded scalar Nash search, independently verified by payoff deviations."""

from itertools import islice, product

import numpy as np
from numpy.typing import NDArray
from pydantic import Field, JsonValue
from scipy.optimize import least_squares

from components.common.math.scalar import (
    OptimizationBudgetExceeded,
    ScalarSearchSettings,
    maximize_scalar,
)
from simulation_core.solver import (
    DifferentiableScalarGameView,
    Equilibrium,
    GameView,
    Solver,
    SolveResult,
)
from simulation_core.types import Action, FrozenModel


class NumericalNashParameters(FrozenModel):
    starts: int = Field(default=9, ge=1, le=27)
    max_root_evaluations: int = Field(default=300, gt=0, le=3000)
    fallback_steps: int = Field(default=60, ge=0, le=300)
    payoff_tolerance: float = Field(default=1e-5, gt=0)
    price_tolerance: float = Field(default=1e-5, gt=0)
    best_response: ScalarSearchSettings = Field(default_factory=ScalarSearchSettings)


class NumericalNashSolver(Solver):
    def solve(self, game: GameView, parameters: dict[str, JsonValue]) -> SolveResult:
        settings = NumericalNashParameters.model_validate(parameters)
        if not isinstance(game, DifferentiableScalarGameView):
            return SolveResult(
                status="unsupported",
                certification="numerical",
                profile_domain="continuous",
                diagnostics={"reason": "Differentiable bounded scalar game required"},
            )
        ids = game.actor_ids()
        domains = [game.action_bounds(aid) for aid in ids]
        lower = np.array([bound[0] for bound in domains])
        widths = np.array([bound[1] - bound[0] for bound in domains])
        attempts: list[dict[str, JsonValue]] = []
        solutions: list[Equilibrium] = []
        scales = max(game.payoff_scale(), 1.0)

        def profile(prices: NDArray[np.float64]) -> tuple[Action, ...]:
            return tuple(game.scalar_action(aid, float(value)) for aid, value in zip(ids, prices))

        def residual(z: NDArray[np.float64]) -> NDArray[np.float64]:
            actions = profile(lower + widths * z)
            gradient = game.own_payoff_gradient(actions)
            normalized = np.array([gradient[aid] for aid in ids]) * widths / scales
            # A bounded positive gradient step preserves the KKT roots without
            # saturating the projection across an entire multi-modal basin.
            step = 0.1 * normalized / (1.0 + np.abs(normalized))
            return z - np.clip(z + step, 0.0, 1.0)

        def snap(prices: NDArray[np.float64]) -> NDArray[np.float64]:
            result = prices.copy()
            for i, (low, high) in enumerate(domains):
                if abs(result[i] - low) <= settings.price_tolerance:
                    result[i] = low
                elif abs(result[i] - high) <= settings.price_tolerance:
                    result[i] = high
            return result

        def verify(prices: NDArray[np.float64], method: str) -> bool:
            prices = snap(prices)
            if any(
                max(abs(prices[i] - game.action_value(eq.actions[i])) for i in range(len(ids)))
                <= settings.price_tolerance
                for eq in solutions
            ):
                return True
            actions = profile(prices)
            outcome = game.evaluate(actions)
            regrets = {}
            checks: dict[str, JsonValue] = {}
            for i, aid in enumerate(ids):

                def objective(value: float, index: int = i, actor_id: str = aid) -> float:
                    candidate = list(actions)
                    candidate[index] = game.scalar_action(actor_id, value)
                    return game.evaluate(candidate).payoffs[actor_id]

                first = maximize_scalar(
                    objective, domains[i], settings.best_response, float(prices[i])
                )
                independent = maximize_scalar(
                    objective,
                    domains[i],
                    settings.best_response,
                    float(prices[i]),
                    independent=True,
                )
                # Do not clamp payoff itself to zero: constrained firms may have unavoidable losses.
                gain = max(0.0, max(first.payoff, independent.payoff) - outcome.payoffs[aid])
                regrets[aid] = gain
                checks[aid] = {
                    "gain": gain,
                    "primary": first.model_dump(mode="json"),
                    "independent": independent.model_dump(mode="json"),
                    "at_lower_bound": float(prices[i]) == domains[i][0],
                    "at_upper_bound": float(prices[i]) == domains[i][1],
                }
            passed = max(regrets.values()) <= settings.payoff_tolerance
            attempts.append(
                {
                    "method": method,
                    "verified": passed,
                    "checks": checks,
                    "projected_gradient_residual": float(
                        np.max(np.abs(residual((prices - lower) / widths)))
                    ),
                }
            )
            if passed:
                solutions.append(Equilibrium(actions=actions, outcome=outcome, regrets=regrets))
            return passed

        try:
            fractions = [
                tuple([0.5] * len(ids)),
                *islice(product((0.1, 0.5, 0.9), repeat=len(ids)), settings.starts),
            ]
            unique_starts = list(dict.fromkeys(fractions))[: settings.starts]
            for start in unique_starts:
                try:
                    root = least_squares(
                        residual,
                        np.array(start),
                        bounds=(np.zeros(len(ids)), np.ones(len(ids))),
                        max_nfev=settings.max_root_evaluations,
                        ftol=1e-11,
                        xtol=1e-11,
                        gtol=1e-11,
                    )
                except (ArithmeticError, ValueError) as exc:
                    attempts.append(
                        {
                            "method": "bounded_least_squares",
                            "success": False,
                            "error_category": type(exc).__name__,
                            "start": list(start),
                        }
                    )
                    continue
                attempts.append(
                    {
                        "method": "bounded_least_squares",
                        "success": bool(root.success),
                        "evaluations": int(root.nfev),
                        "start": list(start),
                        "residual": float(np.max(np.abs(root.fun))),
                    }
                )
                if root.success:
                    verify(lower + widths * root.x, "multistart_candidate")
            if not solutions and settings.fallback_steps:
                prices = lower + 0.5 * widths
                for step in range(settings.fallback_steps):
                    actions = profile(prices)
                    replies = [game.best_response(aid, actions) for aid in ids]
                    target = np.array(
                        [game.action_value(reply.witness_action) for reply in replies]
                    )
                    if max(reply.gain for reply in replies) <= settings.payoff_tolerance:
                        verify(prices, "damped_best_response_fallback")
                        break
                    prices = 0.5 * prices + 0.5 * target
                attempts.append(
                    {"method": "damped_best_response", "steps": step + 1, "found": bool(solutions)}
                )
        except OptimizationBudgetExceeded:
            return SolveResult(
                status="budget_exhausted",
                certification="numerical",
                profile_domain="continuous",
                profiles_evaluated=None,
                total_profiles=None,
                diagnostics={"attempts": [dict(item) for item in attempts]},
            )
        except (ArithmeticError, ValueError) as exc:
            return SolveResult(
                status="failed",
                certification="numerical",
                profile_domain="continuous",
                profiles_evaluated=None,
                total_profiles=None,
                diagnostics={
                    "attempts": [dict(item) for item in attempts],
                    "error_category": type(exc).__name__,
                    "scope": "Numerical failure; no conclusion about equilibrium existence",
                },
            )
        diagnostics: dict[str, JsonValue] = {
            "attempts": [dict(item) for item in attempts],
            "payoff_tolerance": settings.payoff_tolerance,
            "price_tolerance": settings.price_tolerance,
            "scope": "Numerically verified bounded-game candidates; not a proof of global optimality, uniqueness, or completeness",
            "solution_selection": "All distinct equilibria found are retained; no selection or averaging",
            "method": "Multistart projected-gradient roots; grid/local and independent SHGO deviation checks; bounded fallback",
        }
        return SolveResult(
            status="failed" if not solutions else "multiple" if len(solutions) > 1 else "solved",
            equilibria=tuple(solutions),
            certification="numerical",
            profile_domain="continuous",
            profiles_evaluated=None,
            total_profiles=None,
            diagnostics=diagnostics,
        )
