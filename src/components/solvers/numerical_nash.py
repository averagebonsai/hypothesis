"""Multistart bounded scalar Nash search, independently verified by payoff deviations."""

from collections.abc import Sequence
from itertools import islice, product
from math import isfinite

import numpy as np
from numpy.typing import NDArray
from pydantic import AliasChoices, Field, JsonValue
from scipy.optimize import least_squares

from components.common.math.scalar import (
    OptimizationBudgetExceeded,
    ScalarSearchSettings,
)
from components.solvers.requirements import PURE_PAYOFFS, VIEW
from components.solvers.response import scalar_best_response
from simulation_core.contracts import (
    MethodContract,
    MethodRequirement,
    RequirementEvidence,
    checked,
)
from simulation_core.domains import ScalarInterval
from simulation_core.solver import (
    BestResponseResult,
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
    action_tolerance: float = Field(
        default=1e-5, gt=0, validation_alias=AliasChoices("action_tolerance", "price_tolerance")
    )
    best_response: ScalarSearchSettings = Field(default_factory=ScalarSearchSettings)


class NumericalNashSolver(Solver):
    required_game_type = DifferentiableScalarGameView
    result_certification = "numerical"
    profile_domain = "continuous"
    contract = MethodContract(
        name="Multistart scalar numerical Nash search",
        requirements=(
            VIEW,
            PURE_PAYOFFS,
            MethodRequirement(
                id="finite_scalar_boxes",
                description="Each actor chooses one scalar in an ordered finite interval with representable finite width; actor IDs are unique",
            ),
            MethodRequirement(
                id="correct_smooth_gradients",
                enforcement="conditional",
                description="Own-payoff gradients are correct and sufficiently smooth for the projected-gradient root search",
            ),
        ),
        guarantees=(
            "Returned candidates pass the configured numerical unilateral-deviation searches within payoff tolerance",
        ),
        limitations=(
            "No requirement or certification of global convexity/concavity",
            "No proof of a global best response, uniqueness, completeness, or equilibrium existence",
            "Independent searches can still miss the same narrow profitable deviation",
            "Convergence and sampled derivative checks do not establish global mathematical properties",
            "Budgets are per search, not a total wall-clock or aggregate objective budget",
        ),
    )

    def requirement_evidence(
        self, game: GameView, parameters: dict[str, JsonValue]
    ) -> tuple[RequirementEvidence, ...]:
        evidence = super().requirement_evidence(game, parameters)
        NumericalNashParameters.from_json_values(parameters)
        if not isinstance(game, DifferentiableScalarGameView):
            return evidence
        try:
            self.validate_game(game)
        except (ValueError, TypeError) as exc:
            return (*evidence, checked("finite_scalar_boxes", False, str(exc)))
        return (
            *evidence,
            checked(
                "finite_scalar_boxes",
                True,
                "Actor identity and finite interval constraints checked without searching payoffs",
            ),
        )

    def validate_game(self, game: GameView) -> None:
        super().validate_game(game)
        if not isinstance(game, DifferentiableScalarGameView):
            raise TypeError("Differentiable scalar game required")
        ids = game.actor_ids()
        if not ids or len(set(ids)) != len(ids):
            raise ValueError("Scalar game requires unique actors and nonempty domains")
        for aid in ids:
            lower, upper = game.action_bounds(aid)
            ScalarInterval(lower=lower, upper=upper)
            if not isfinite(upper - lower):
                raise ValueError("Scalar interval width must be representable and finite")

    def best_responses(
        self, game: GameView, profile: Sequence[Action], parameters: dict[str, JsonValue]
    ) -> dict[str, BestResponseResult]:
        self.validate_game(game)
        if not isinstance(game, DifferentiableScalarGameView):
            raise TypeError("Differentiable scalar game required")
        settings = NumericalNashParameters.from_json_values(parameters)
        return {
            aid: scalar_best_response(game, aid, profile, settings.best_response, cross_check=True)
            for aid in game.actor_ids()
        }

    def _solve(self, game: GameView, parameters: dict[str, JsonValue]) -> SolveResult:
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

        def profile(values: NDArray[np.float64]) -> tuple[Action, ...]:
            return tuple(game.scalar_action(aid, float(value)) for aid, value in zip(ids, values))

        def residual(z: NDArray[np.float64]) -> NDArray[np.float64]:
            actions = profile(lower + widths * z)
            gradient = game.own_payoff_gradient(actions)
            normalized = np.array([gradient[aid] for aid in ids]) * widths / scales
            # A bounded positive gradient step preserves the KKT roots without
            # saturating the projection across an entire multi-modal basin.
            step = 0.1 * normalized / (1.0 + np.abs(normalized))
            return z - np.clip(z + step, 0.0, 1.0)

        def snap(values: NDArray[np.float64]) -> NDArray[np.float64]:
            result = values.copy()
            for i, (low, high) in enumerate(domains):
                if abs(result[i] - low) <= settings.action_tolerance:
                    result[i] = low
                elif abs(result[i] - high) <= settings.action_tolerance:
                    result[i] = high
            return result

        def verify(values: NDArray[np.float64], method: str) -> bool:
            values = snap(values)
            if any(
                max(abs(values[i] - game.action_value(eq.actions[i])) for i in range(len(ids)))
                <= settings.action_tolerance
                for eq in solutions
            ):
                return True
            actions = profile(values)
            outcome = game.evaluate(actions)
            regrets = {}
            checks: dict[str, JsonValue] = {}
            for i, aid in enumerate(ids):
                response = scalar_best_response(
                    game, aid, actions, settings.best_response, cross_check=True
                )
                regrets[aid] = response.gain
                checks[aid] = {
                    "gain": response.gain,
                    **response.diagnostics,
                    "at_lower_bound": float(values[i]) == domains[i][0],
                    "at_upper_bound": float(values[i]) == domains[i][1],
                }
            passed = max(regrets.values()) <= settings.payoff_tolerance
            attempts.append(
                {
                    "method": method,
                    "verified": passed,
                    "checks": checks,
                    "projected_gradient_residual": float(
                        np.max(np.abs(residual((values - lower) / widths)))
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
                values = lower + 0.5 * widths
                for step in range(settings.fallback_steps):
                    actions = profile(values)
                    replies = [
                        scalar_best_response(game, aid, actions, settings.best_response)
                        for aid in ids
                    ]
                    target = np.array(
                        [game.action_value(reply.witness_action) for reply in replies]
                    )
                    if max(reply.gain for reply in replies) <= settings.payoff_tolerance:
                        verify(values, "damped_best_response_fallback")
                        break
                    values = 0.5 * values + 0.5 * target
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
            "action_tolerance": settings.action_tolerance,
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
