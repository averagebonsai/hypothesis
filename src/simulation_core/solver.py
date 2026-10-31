"""Mathematical benchmarks query a read-only game; they never commit actor actions."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Literal

from pydantic import Field, JsonValue

from .types import Action, FrozenModel, Outcome


class GameView(ABC):
    @abstractmethod
    def actor_ids(self) -> tuple[str, ...]: ...

    @abstractmethod
    def actions(self, actor_id: str) -> tuple[Action, ...]: ...

    @abstractmethod
    def evaluate(self, profile: Sequence[Action]) -> Outcome: ...


class Equilibrium(FrozenModel):
    actions: tuple[Action, ...]
    outcome: Outcome
    regrets: dict[str, float]


class SolveResult(FrozenModel):
    solution_concept: Literal["pure_nash"] = "pure_nash"
    status: Literal["solved", "multiple", "no_pure_equilibrium", "budget_exhausted", "failed"]
    equilibria: tuple[Equilibrium, ...] = ()
    profiles_evaluated: int = Field(default=0, ge=0)
    total_profiles: int = Field(default=0, ge=0)
    diagnostics: dict[str, JsonValue] = Field(default_factory=dict)


class Solver(ABC):
    @abstractmethod
    def solve(self, game: GameView, parameters: dict[str, JsonValue]) -> SolveResult: ...


def deviation_regrets(game: GameView, profile: Sequence[Action]) -> dict[str, float]: 
    ## this doesn't seem to be experiment-specific, more for game theory experiments
    baseline = game.evaluate(profile)
    regrets = {}
    for index, action in enumerate(profile):
        best = baseline.payoffs[action.actor_id]
        for alternative in game.actions(action.actor_id):
            candidate = list(profile)
            candidate[index] = alternative
            best = max(best, game.evaluate(candidate).payoffs[action.actor_id])
        regrets[action.actor_id] = max(0.0, best - baseline.payoffs[action.actor_id])
    return regrets
