from collections.abc import Sequence
from typing import Any, ClassVar

import numpy as np
from pydantic import JsonValue

from experiment_extension.game_view import AllocationGameView
from simulation_core.contracts import (
    MethodContract,
    MethodRequirement,
    RequirementEvidence,
    checked,
)
from simulation_core.solver import Action, Equilibrium, GameView, Solver, SolveResult


def project_simplex(target: Sequence[float], budget: float) -> list[float]:
    """Water-filling projection of target onto {x>=0, sum x=budget}; general dims>=2."""
    t = [float(x) for x in target]
    s = sorted(t, reverse=True)
    n = len(s)
    cumsum = 0.0
    lam = (sum(s) - budget) / n
    for k, v in enumerate(s, start=1):
        cumsum += v
        cand = (cumsum - budget) / k
        if k == n or cand >= s[k]:
            lam = cand
            break
    return [max(0.0, x - lam) for x in t]


def _read_params(game: AllocationGameView) -> tuple[float, list[float]]:
    budget_raw = game.config.world.parameters["budget"]
    target_raw = game.config.world.parameters["target"]
    if isinstance(budget_raw, bool) or not isinstance(budget_raw, (int, float)):
        raise TypeError("budget must be a number")
    if not isinstance(target_raw, (list, tuple)):
        raise TypeError("target must be a vector")
    budget = float(budget_raw)
    target: list[float] = []
    for x in target_raw:
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            raise TypeError("target entries must be numbers")
        target.append(float(x))
    return budget, target


class AllocationSolver(Solver):
    """Analytic single-actor optimum via simplex projection; not a multiplayer equilibrium."""

    required_game_type: ClassVar[type[GameView] | None] = AllocationGameView
    result_certification: ClassVar[str] = "analytic"  # type: ignore[assignment]
    solution_concept: ClassVar[str] = "pure_nash"  # type: ignore[assignment]
    profile_domain: ClassVar[str] = "continuous"  # type: ignore[assignment]
    contract: ClassVar[MethodContract] = MethodContract(
        name="Simplex projection optimum",
        requirements=(
            MethodRequirement(id="view", description="Game view capability available"),
            MethodRequirement(
                id="valid_inputs",
                description="Positive budget and finite target vector of dimension >=2",
            ),
        ),
        guarantees=(
            "Analytic projection of target onto fixed-sum nonnegative simplex"
            " is the single-actor optimum",
        ),
        limitations=(
            "Single-actor optimum only; not a multiplayer equilibrium",
            "Applies to squared-distance objective with sum equality and nonnegativity",
        ),
    )

    def requirement_evidence(
        self, game: GameView, parameters: dict[str, JsonValue]
    ) -> tuple[RequirementEvidence, ...]:
        ok_view = isinstance(game, AllocationGameView)
        valid = False
        reason = "Game-view capability checked"
        if ok_view:
            try:
                assert isinstance(game, AllocationGameView)
                budget, target = _read_params(game)
                valid = (
                    bool(budget > 0)
                    and len(target) >= 2
                    and all(bool(np.isfinite(float(x))) for x in target)
                )
                reason = "Positive budget and finite target vector of dimension >=2 checked"
            except (TypeError, ValueError, KeyError):
                valid = False
        return (
            checked("view", ok_view, "Game-view capability checked against the solver contract"),
            checked("valid_inputs", valid, reason),
        )

    def _solve(self, game: GameView, parameters: dict[str, JsonValue]) -> SolveResult:
        assert isinstance(game, AllocationGameView)
        budget, target = _read_params(game)
        opt = project_simplex(target, budget)
        aid = game.actor_ids()[0]
        payload: dict[str, Any] = {"allocation": opt}
        action = Action(actor_id=aid, kind="allocate", payload=payload)
        outcome = game.evaluate((action,))
        eq = Equilibrium(actions=(action,), outcome=outcome, regrets={aid: 0.0})
        diag: dict[str, Any] = {"method": "water-filling simplex projection", "optimum": opt}
        return SolveResult(
            status="solved",
            certification="analytic",
            solution_concept="pure_nash",
            profile_domain="continuous",
            profiles_evaluated=1,
            total_profiles=1,
            equilibria=(eq,),
            diagnostics=diag,  # type: ignore[arg-type]
        )
