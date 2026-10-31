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
    def evaluate(self, profile: Sequence[Action]) -> Outcome: ...


class FiniteGameView(GameView):
    @abstractmethod
    def actions(self, actor_id: str) -> tuple[Action, ...]: ...


class BestResponseResult(FrozenModel):
    actor_id: str
    current_payoff: float
    supremum_payoff: float
    gain: float = Field(ge=0)
    attained: bool
    maximizing_action: Action | None = None
    witness_action: Action
    witness_payoff: float
    certification: Literal["analytic", "numerical"] = "analytic"
    diagnostics: dict[str, JsonValue] = Field(default_factory=dict)


class BestResponseGameView(GameView):
    """Continuous games can report a supremum without inventing an attained optimum."""

    @abstractmethod
    def best_response(self, actor_id: str, profile: Sequence[Action]) -> BestResponseResult: ...


class DifferentiableScalarGameView(BestResponseGameView):
    """One bounded scalar action per actor, with own-payoff derivatives."""

    @abstractmethod
    def action_bounds(self, actor_id: str) -> tuple[float, float]: ...

    @abstractmethod
    def scalar_action(self, actor_id: str, value: float) -> Action: ...

    @abstractmethod
    def action_value(self, action: Action) -> float: ...

    @abstractmethod
    def own_payoff_gradient(self, profile: Sequence[Action]) -> dict[str, float]: ...

    def payoff_scale(self) -> float:
        return 1.0


class Equilibrium(FrozenModel):
    actions: tuple[Action, ...]
    outcome: Outcome
    regrets: dict[str, float]


class SolveResult(FrozenModel):
    solution_concept: Literal["pure_nash"] = "pure_nash"
    status: Literal[
        "solved", "multiple", "no_pure_equilibrium", "budget_exhausted", "unsupported", "failed"
    ]
    equilibria: tuple[Equilibrium, ...] = ()
    certification: Literal["analytic", "numerical"] = "analytic"
    profile_domain: Literal["finite", "continuous"] = "finite"
    profiles_evaluated: int | None = Field(default=0, ge=0)
    total_profiles: int | None = Field(default=0, ge=0)
    diagnostics: dict[str, JsonValue] = Field(default_factory=dict)


class Solver(ABC):
    @abstractmethod
    def solve(self, game: GameView, parameters: dict[str, JsonValue]) -> SolveResult: ...


def deviation_regrets(game: GameView, profile: Sequence[Action]) -> dict[str, float]:
    """Game-theory diagnostic shared by benchmarks, independent of the execution loop."""
    if isinstance(game, BestResponseGameView):
        return {aid: game.best_response(aid, profile).gain for aid in game.actor_ids()}
    if not isinstance(game, FiniteGameView):
        raise TypeError("Game view supplies neither finite actions nor a best-response oracle")
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
