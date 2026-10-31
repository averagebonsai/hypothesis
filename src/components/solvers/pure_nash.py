"""Exhaustive finite-game benchmark with an explicit profile budget and tolerance."""

from itertools import product
from math import prod
from typing import Literal

from pydantic import Field, JsonValue

from simulation_core.solver import Equilibrium, GameView, Solver, SolveResult
from simulation_core.types import FrozenModel


class PureNashParameters(FrozenModel):
    max_profiles: int = Field(default=10000, gt=0)
    payoff_tolerance: float = Field(default=1e-9, ge=0)


class PureNashSolver(Solver):
    def solve(self, game: GameView, parameters: dict[str, JsonValue]) -> SolveResult:
        params = PureNashParameters.model_validate(parameters)
        ids = game.actor_ids()
        choices = [game.actions(aid) for aid in ids]
        if not ids or any(not actions for actions in choices):
            raise ValueError("Finite game requires actors and nonempty action domains")
        size = prod(len(actions) for actions in choices)
        diagnostics: dict[str, JsonValue] = {
            "payoff_tolerance": params.payoff_tolerance,
            "scope": "Pure strategies only; no conclusion about mixed equilibria.",
        }
        if size > params.max_profiles:
            return SolveResult(
                status="budget_exhausted",
                total_profiles=size,
                diagnostics={**diagnostics, "max_profiles": params.max_profiles},
            )
        profiles = list(product(*(range(len(actions)) for actions in choices)))
        payoffs = {
            key: game.evaluate(tuple(choices[i][j] for i, j in enumerate(key))) for key in profiles
        }
        equilibria = []
        for key in profiles:
            outcome = payoffs[key]
            regrets = {}
            for i, aid in enumerate(ids):
                best = max(
                    payoffs[(*key[:i], j, *key[i + 1 :])].payoffs[aid]
                    for j in range(len(choices[i]))
                )
                regrets[aid] = max(0.0, best - outcome.payoffs[aid])
            if all(value <= params.payoff_tolerance for value in regrets.values()):
                equilibria.append(
                    Equilibrium(
                        actions=tuple(choices[i][j] for i, j in enumerate(key)),
                        outcome=outcome,
                        regrets=regrets,
                    )
                )
        status: Literal["no_pure_equilibrium", "solved", "multiple"] = (
            "no_pure_equilibrium"
            if not equilibria
            else "solved"
            if len(equilibria) == 1
            else "multiple"
        )
        return SolveResult(
            status=status,
            equilibria=tuple(equilibria),
            profiles_evaluated=size,
            total_profiles=size,
            diagnostics=diagnostics,
        )
