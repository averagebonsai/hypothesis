"""Independent benchmark reporting over a copy of the compared round's precommit world."""

import hashlib
import json
from typing import TYPE_CHECKING

from pydantic import Field, JsonValue

from .solver import BestResponseGameView, BestResponseResult, SolveResult, deviation_regrets
from .types import Action, FrozenModel, RunResult, SimulationConfig

if TYPE_CHECKING:
    from .registry import ComponentRegistry


def numeric_deltas(
    values: dict[str, JsonValue], reference: dict[str, JsonValue]
) -> dict[str, float]:
    result = {}
    for key, value in values.items():
        other = reference.get(key)
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and isinstance(other, (int, float))
            and not isinstance(other, bool)
        ):
            result[key] = float(value) - float(other)
    return result


class EquilibriumComparison(FrozenModel):
    equilibrium_index: int
    payoff_deltas: dict[str, float]
    action_differences: dict[str, bool]
    numeric_action_deltas: dict[str, dict[str, float]] = Field(default_factory=dict)
    metric_deltas: dict[str, float] = Field(default_factory=dict)


class BenchmarkReport(FrozenModel):
    config_sha256: str
    comparison_tick: int | None = None
    result: SolveResult
    observed_actions: tuple[Action, ...] = ()
    observed_regrets: dict[str, float] = Field(default_factory=dict)
    observed_best_responses: dict[str, BestResponseResult] = Field(default_factory=dict)
    comparisons: tuple[EquilibriumComparison, ...] = ()


class BenchmarkRunner:
    def __init__(self, registry: "ComponentRegistry") -> None:
        self.registry = registry

    def run(self, config: SimulationConfig, run: RunResult) -> BenchmarkReport:
        digest = hashlib.sha256(
            json.dumps(
                config.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest()
        spec = config.benchmark
        if spec is None:
            raise ValueError("No benchmark configured")
        try:
            tick = spec.comparison_tick or run.final_state.tick
            event = next(
                event
                for event in run.events
                if event.kind == "committed" and event.state.tick == tick
            )
            previous = next(event.state for event in run.events if event.state.tick == tick - 1)
            mechanism = self.registry.mechanisms[config.mechanism_id]()
            game = self.registry.game_views[spec.game_view_id](
                config.model_copy(deep=True), previous.model_copy(deep=True), mechanism
            )
            solver = self.registry.solvers[spec.solver_id]()
            solved = solver.solve(game, dict(spec.parameters))
            if solved.status in {"failed", "budget_exhausted", "unsupported"}:
                return BenchmarkReport(
                    config_sha256=digest,
                    comparison_tick=tick,
                    result=solved,
                    observed_actions=event.actions,
                )
            by_actor = {action.actor_id: action for action in event.actions}
            if set(by_actor) != set(game.actor_ids()):
                raise ValueError("Benchmark requires a complete joint action profile")
            profile = tuple(by_actor[aid] for aid in game.actor_ids())
            observed = game.evaluate(profile)
            comparisons = []
            for index, equilibrium in enumerate(solved.equilibria):
                reference = {a.actor_id: a for a in equilibrium.actions}
                comparisons.append(
                    EquilibriumComparison(
                        equilibrium_index=index,
                        numeric_action_deltas={
                            aid: numeric_deltas(by_actor[aid].payload, reference[aid].payload)
                            for aid in game.actor_ids()
                        },
                        metric_deltas=numeric_deltas(observed.metrics, equilibrium.outcome.metrics),
                        payoff_deltas={
                            aid: observed.payoffs[aid] - equilibrium.outcome.payoffs[aid]
                            for aid in game.actor_ids()
                        },
                        action_differences={
                            aid: by_actor[aid] != reference[aid] for aid in game.actor_ids()
                        },
                    )
                )
            responses = (
                {aid: game.best_response(aid, profile) for aid in game.actor_ids()}
                if isinstance(game, BestResponseGameView)
                else {}
            )
            return BenchmarkReport(
                config_sha256=digest,
                comparison_tick=tick,
                result=solved,
                observed_actions=profile,
                observed_regrets={aid: response.gain for aid, response in responses.items()}
                if responses
                else deviation_regrets(game, profile),
                observed_best_responses=responses,
                comparisons=tuple(comparisons),
            )
        except (ArithmeticError, ValueError, StopIteration) as exc:
            # Numerical/adapter failures are separate from the completed primary actor run.
            return BenchmarkReport(
                config_sha256=digest,
                result=SolveResult(
                    status="failed", diagnostics={"error_category": type(exc).__name__}
                ),
            )
