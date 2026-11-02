"""Exhaustive finite-game benchmark with an explicit profile budget and tolerance."""

from itertools import product
from math import prod
from typing import Literal

from pydantic import Field, JsonValue

from components.solvers.requirements import PURE_PAYOFFS, VIEW
from simulation_core.contracts import (
    MethodContract,
    MethodRequirement,
    RequirementEvidence,
    checked,
)
from simulation_core.solver import Equilibrium, FiniteGameView, GameView, Solver, SolveResult
from simulation_core.types import FrozenModel


class PureNashParameters(FrozenModel):
    max_profiles: int = Field(default=10000, gt=0)
    payoff_tolerance: float = Field(default=1e-9, ge=0)


class PureNashSolver(Solver):
    required_game_type = FiniteGameView
    contract = MethodContract(
        name="Exhaustive finite pure-Nash enumeration",
        requirements=(
            VIEW,
            PURE_PAYOFFS,
            MethodRequirement(
                id="finite_actions",
                description="Unique actors, finite nonempty correctly owned action lists",
            ),
            MethodRequirement(
                id="enumeration_budget",
                enforcement="conditional",
                description="The profile budget permits complete enumeration",
            ),
        ),
        guarantees=(
            "After complete enumeration: all pure equilibria within payoff tolerance, or absence of a pure equilibrium in the supplied finite game",
        ),
        limitations=(
            "No mixed-strategy result",
            "No convexity, concavity, continuity, or differentiability requirement",
            "Budget exhaustion gives no existence conclusion",
            "Floating-point payoffs and configured tolerance qualify the result",
        ),
    )

    def requirement_evidence(
        self, game: GameView, parameters: dict[str, JsonValue]
    ) -> tuple[RequirementEvidence, ...]:
        evidence = super().requirement_evidence(game, parameters)
        settings = PureNashParameters.from_json_values(parameters)
        if not isinstance(game, FiniteGameView):
            return evidence
        ids = game.actor_ids()
        choices = [game.actions(aid) for aid in ids]
        valid = (
            bool(ids)
            and len(set(ids)) == len(ids)
            and all(choices)
            and all(
                len({action.model_dump_json() for action in actions}) == len(actions)
                for actions in choices
            )
            and all(
                action.actor_id == aid for aid, actions in zip(ids, choices) for action in actions
            )
        )
        return (
            *evidence,
            checked(
                "finite_actions", valid, "Action domains enumerated without evaluating payoffs"
            ),
            checked(
                "enumeration_budget",
                prod(len(actions) for actions in choices) <= settings.max_profiles,
                "Cartesian profile count compared with max_profiles; exhaustion remains a separate result status",
            ),
        )

    def _solve(self, game: GameView, parameters: dict[str, JsonValue]) -> SolveResult:
        params = PureNashParameters.model_validate(parameters)
        if not isinstance(game, FiniteGameView):
            return SolveResult(
                status="unsupported", diagnostics={"reason": "Finite action enumeration required"}
            )
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
        if any(set(outcome.payoffs) != set(ids) for outcome in payoffs.values()):
            raise ValueError("Finite payoff evaluation must return exactly all actors' payoffs")
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
