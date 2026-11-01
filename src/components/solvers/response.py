"""Shared scalar unilateral search for adapters, fallback, and benchmark diagnostics."""

from collections.abc import Callable, Sequence

from components.common.math.scalar import ScalarSearchSettings, maximize_scalar
from simulation_core.solver import BestResponseResult, DifferentiableScalarGameView
from simulation_core.types import Action


def unilateral_objective(
    game: DifferentiableScalarGameView, actor_id: str, profile: Sequence[Action]
) -> Callable[[float], float]:
    """Hold every rival action fixed, preserving the game's actor ordering."""
    actions = {action.actor_id: action.model_copy(deep=True) for action in profile}
    if (
        len(actions) != len(profile)
        or set(actions) != set(game.actor_ids())
        or actor_id not in actions
    ):
        raise ValueError("Unilateral search requires a complete profile and a known actor")

    def objective(value: float) -> float:
        candidate = tuple(
            game.scalar_action(aid, value) if aid == actor_id else actions[aid]
            for aid in game.actor_ids()
        )
        return game.evaluate(candidate).payoffs[actor_id]

    return objective


def scalar_best_response(
    game: DifferentiableScalarGameView,
    actor_id: str,
    profile: Sequence[Action],
    settings: ScalarSearchSettings,
    *,
    cross_check: bool = False,
) -> BestResponseResult:
    objective = unilateral_objective(game, actor_id, profile)
    current_action = next(action for action in profile if action.actor_id == actor_id)
    current_value = game.action_value(current_action)
    current_payoff = objective(current_value)
    primary = maximize_scalar(objective, game.action_bounds(actor_id), settings, current_value)
    checks = [primary]
    if cross_check:
        checks.append(
            maximize_scalar(
                objective, game.action_bounds(actor_id), settings, current_value, independent=True
            )
        )
    best = max(checks, key=lambda item: item.objective_value)
    action = game.scalar_action(actor_id, best.value)
    return BestResponseResult(
        actor_id=actor_id,
        current_payoff=current_payoff,
        estimated_best_payoff=best.objective_value,
        gain=max(0.0, best.objective_value - current_payoff),
        # No global optimum or attainment certificate follows from numerical search.
        attained=None,
        maximizing_action=None,
        witness_action=action,
        witness_payoff=best.objective_value,
        certification="numerical",
        diagnostics={
            "primary": primary.model_dump(mode="json"),
            "independent": checks[1].model_dump(mode="json") if cross_check else None,
            "settings": settings.model_dump(mode="json"),
            "qualification": "Best-found feasible candidate; supremum and global attainment are not certified",
        },
    )
