"""Mathematical benchmarks query a read-only game; they never commit actor actions."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import ClassVar, Literal

from pydantic import Field, JsonValue

from .analysis import AnalysisResult
from .types import Action, Event, FrozenModel, Outcome


class ObservedProfile(FrozenModel):
    actions: tuple[Action, ...]
    source_ticks: dict[str, int]
    complete: bool


class GameView(ABC):
    def observed_profile(self, events: Sequence[Event], tick: int) -> ObservedProfile:
        event = next(
            event for event in events if event.kind == "committed" and event.state.tick == tick
        )
        by_actor = {action.actor_id: action for action in event.actions}
        if len(by_actor) != len(event.actions) or set(by_actor) - set(self.actor_ids()):
            raise ValueError("Invalid actors in observed profile")
        return ObservedProfile(
            actions=tuple(by_actor[aid] for aid in self.actor_ids() if aid in by_actor),
            source_ticks={aid: tick for aid in by_actor},
            complete=set(by_actor) == set(self.actor_ids()),
        ).model_copy(deep=True)

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
    supremum_payoff: float | None = None
    estimated_best_payoff: float | None = None
    gain: float = Field(ge=0)
    attained: bool | None
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


class SolveResult(AnalysisResult):
    """Equilibrium-specific result; general optimization tools need not return equilibria."""

    certification: Literal["analytic", "numerical"] = "analytic"
    solution_concept: Literal["pure_nash", "subgame_perfect"] = "pure_nash"
    status: Literal[
        "solved", "multiple", "no_pure_equilibrium", "budget_exhausted", "unsupported", "failed"
    ]
    equilibria: tuple[Equilibrium, ...] = ()
    profile_domain: Literal["finite", "continuous"] = "finite"
    profiles_evaluated: int | None = Field(default=0, ge=0)
    total_profiles: int | None = Field(default=0, ge=0)


class StrategicDeviationAnalysis(FrozenModel):
    gains: dict[str, float]
    interpretations: dict[str, str]
    details: dict[str, JsonValue] = Field(default_factory=dict)


class SequentialGameView(GameView):
    """One episode, possibly multiple commits; never silently mix stages or rounds."""

    @abstractmethod
    def action_stages(self) -> tuple[tuple[str, ...], ...]: ...

    @abstractmethod
    def strategic_deviations(
        self, profile: Sequence[Action], references: Sequence[Equilibrium]
    ) -> StrategicDeviationAnalysis: ...

    def observed_profile(self, events: Sequence[Event], tick: int) -> ObservedProfile:
        next(event for event in events if event.kind == "committed" and event.state.tick == tick)
        commits = [
            event for event in events if event.kind == "committed" and event.state.tick <= tick
        ]
        stages = self.action_stages()
        if len(commits) > len(stages):
            raise ValueError("Sequential view expects exactly one episode")
        by_actor = {}
        sources = {}
        for index, event in enumerate(commits):
            ids = [action.actor_id for action in event.actions]
            if (
                event.state.tick != index + 1
                or len(ids) != len(set(ids))
                or set(ids) != set(stages[index])
            ):
                raise ValueError("Committed stages do not match the game's decision order")
            for action in event.actions:
                if action.actor_id in by_actor:
                    raise ValueError("Profile adapter requires one decision per actor per episode")
                by_actor[action.actor_id] = action
                sources[action.actor_id] = event.state.tick
        return ObservedProfile(
            actions=tuple(by_actor[aid] for aid in self.actor_ids() if aid in by_actor),
            source_ticks=sources,
            complete=len(commits) == len(stages) and set(by_actor) == set(self.actor_ids()),
        ).model_copy(deep=True)


class TwoStageGameView(SequentialGameView):
    """Leader commitment followed by a chosen optimal follower continuation."""

    @abstractmethod
    def leader_id(self) -> str: ...

    @abstractmethod
    def follower_id(self) -> str: ...

    @abstractmethod
    def follower_response(self, leader_action: Action) -> Action: ...

    def action_stages(self) -> tuple[tuple[str, ...], ...]:
        return ((self.leader_id(),), (self.follower_id(),))

    def strategic_deviations(
        self, profile: Sequence[Action], references: Sequence[Equilibrium]
    ) -> StrategicDeviationAnalysis:
        leader, follower = self.leader_id(), self.follower_id()
        actions = {action.actor_id: action for action in profile}
        observed = self.evaluate(profile)
        reply = self.follower_response(actions[leader])
        continuation = self.evaluate((actions[leader], reply))
        best_leader = max(item.outcome.payoffs[leader] for item in references)
        return StrategicDeviationAnalysis(
            gains={
                leader: max(0.0, best_leader - continuation.payoffs[leader]),
                follower: max(0.0, continuation.payoffs[follower] - observed.payoffs[follower]),
            },
            interpretations={
                leader: "Gain along the rational follower-response curve, relative to the observed leader commitment",
                follower: "Conditional gain with the observed leader commitment held fixed",
            },
            details={
                "anticipated_follower_at_observed_commitment": reply.model_dump(mode="json"),
                "anticipated_leader_payoff": continuation.payoffs[leader],
                "actual_leader_payoff": observed.payoffs[leader],
                "optimal_anticipated_leader_payoff": best_leader,
                "qualification": "One observed follower action does not identify its full strategy; leader gain assumes the benchmark continuation.",
            },
        )


class Solver(ABC):
    """Game-equilibrium analysis. Compatibility checking never runs the search."""

    required_game_type: ClassVar[type[GameView] | None] = None

    def validate_game(self, game: GameView) -> None:
        if self.required_game_type is not None and not isinstance(game, self.required_game_type):
            raise TypeError(
                f"{type(self).__name__} requires {self.required_game_type.__name__}; got {type(game).__name__}"
            )

    def best_responses(
        self, game: GameView, profile: Sequence[Action], parameters: dict[str, JsonValue]
    ) -> dict[str, BestResponseResult]:
        """Observed diagnostics, overridable to reuse the solver's configured search settings."""
        return (
            {aid: game.best_response(aid, profile) for aid in game.actor_ids()}
            if isinstance(game, BestResponseGameView)
            else {}
        )

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
