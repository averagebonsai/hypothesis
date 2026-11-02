"""A vector decision on a simplex, reusing the existing runtime and benchmark API."""

from collections.abc import Sequence
from math import isclose, isfinite

from pydantic import BaseModel, Field, JsonValue

from simulation_core.contracts import MethodContract, RequirementEvidence, checked
from simulation_core.game_view import MechanismGameView
from simulation_core.mechanism import Mechanism
from simulation_core.solver import (
    BestResponseGameView,
    BestResponseResult,
    Equilibrium,
    GameView,
    Solver,
    SolveResult,
)
from simulation_core.types import (
    Action,
    FrozenModel,
    Outcome,
    TransitionResult,
    WorldConfig,
    WorldState,
)

CONTRACT_DATA: dict[str, JsonValue] = {
    "name": "Euclidean projection onto a fixed-budget simplex",
    "requirements": [
        {"id": "view", "description": "The allocation game view is available"},
        {
            "id": "quadratic_simplex",
            "description": "One vector actor maximizes negative squared distance to a fixed target on a nonnegative fixed-budget simplex",
        },
    ],
    "guarantees": [
        "The simplex projection is a global optimum of the specified quadratic allocation objective"
    ],
    "limitations": [
        "Not an optimizer for arbitrary vector objectives or general nonlinear constraints",
        "Floating-point arithmetic and feasibility tolerance apply",
        "A one-actor Nash optimum is the actor's own optimum, not a multiplayer equilibrium claim",
    ],
}


class AllocationParameters(FrozenModel):
    budget: float = Field(gt=0)
    target: tuple[float, ...] = Field(min_length=2)


class AllocationPayload(FrozenModel):
    allocation: tuple[float, ...] = Field(min_length=2)


def project_simplex(target: tuple[float, ...], budget: float) -> tuple[float, ...]:
    parameters = AllocationParameters(budget=budget, target=target)
    ordered = sorted(parameters.target, reverse=True)
    cumulative = 0.0
    threshold = 0.0
    for count, value in enumerate(ordered, 1):
        cumulative += value
        if not isfinite(cumulative):
            raise ArithmeticError("Projection arithmetic exceeded finite precision")
        candidate = (cumulative - parameters.budget) / count
        if value > candidate:
            threshold = candidate
    result = tuple(max(value - threshold, 0.0) for value in parameters.target)
    if not all(isfinite(value) for value in result) or not isclose(
        sum(result), budget, rel_tol=1e-10, abs_tol=1e-10
    ):
        raise ArithmeticError("Projection is not numerically feasible at the declared tolerance")
    return result


class AllocationMechanism(Mechanism):
    requires_joint_actions = True

    def required_action_schemas(self, config: WorldConfig) -> dict[str, dict[str, type[BaseModel]]]:
        return {actor.id: {"allocate": AllocationPayload} for actor in config.actors}

    def validate_config(self, config: WorldConfig) -> None:
        AllocationParameters.from_json_values(config.parameters)
        if len(config.actors) != 1:
            raise ValueError("Allocation experiment requires one actor")

    def validate_actions(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> None:
        parameters = AllocationParameters.from_json_values(config.parameters)
        if (
            len(actions) != 1
            or actions[0].actor_id != config.actors[0].id
            or actions[0].kind != "allocate"
        ):
            raise ValueError("Expected the allocator's action")
        allocation = AllocationPayload.from_json_values(actions[0].payload).allocation
        if len(allocation) != len(parameters.target) or min(allocation) < 0:
            raise ValueError("Invalid allocation dimension or sign")
        if not isclose(sum(allocation), parameters.budget, rel_tol=1e-10, abs_tol=1e-10):
            raise ValueError("Allocation must exhaust the budget")

    def evaluate(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> Outcome:
        self.validate_actions(config, state, actions)
        parameters = AllocationParameters.from_json_values(config.parameters)
        allocation = AllocationPayload.from_json_values(actions[0].payload).allocation
        score = -sum((value - target) ** 2 for value, target in zip(allocation, parameters.target))
        return Outcome(
            payoffs={actions[0].actor_id: score}, metrics={"allocation": list(allocation)}
        )

    def transition(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> TransitionResult:
        return TransitionResult(
            public={**state.public, "allocation": actions[0].payload["allocation"]},
            outcome=self.evaluate(config, state, actions),
        )

    def validate_state(self, config: WorldConfig, state: WorldState) -> None:
        if state.tick not in {0, 1}:
            raise ValueError("One allocation decision per experiment")
        if state.tick:
            self.validate_actions(
                config,
                state,
                (
                    Action(
                        actor_id=config.actors[0].id,
                        kind="allocate",
                        payload={"allocation": state.public["allocation"]},
                    ),
                ),
            )


class AllocationGameView(MechanismGameView, BestResponseGameView):
    def best_response(self, actor_id: str, profile: Sequence[Action]) -> BestResponseResult:
        if actor_id != self.actor_ids()[0]:
            raise ValueError("Unknown actor")
        parameters = AllocationParameters.from_json_values(self.config.world.parameters)
        action = Action(
            actor_id=actor_id,
            kind="allocate",
            payload={"allocation": list(project_simplex(parameters.target, parameters.budget))},
        )
        current = self.evaluate(profile).payoffs[actor_id]
        optimum = self.evaluate((action,)).payoffs[actor_id]
        return BestResponseResult(
            actor_id=actor_id,
            current_payoff=current,
            supremum_payoff=optimum,
            gain=max(0.0, optimum - current),
            attained=True,
            maximizing_action=action,
            witness_action=action,
            witness_payoff=optimum,
        )


class AllocationSolver(Solver):
    required_game_type = AllocationGameView
    profile_domain = "continuous"
    contract = MethodContract.from_json_values(CONTRACT_DATA)

    def requirement_evidence(
        self, game: GameView, parameters: dict[str, JsonValue]
    ) -> tuple[RequirementEvidence, ...]:
        return (
            *super().requirement_evidence(game, parameters),
            checked(
                "quadratic_simplex",
                type(game) is AllocationGameView and type(game.mechanism) is AllocationMechanism,
                "Squared distance has Hessian 2I; the nonnegative fixed-sum simplex is convex. The sorting projection solves its KKT threshold conditions.",
                basis="analytic_argument",
            ),
        )

    def _solve(self, game: GameView, parameters: dict[str, JsonValue]) -> SolveResult:
        if not isinstance(game, AllocationGameView):
            raise TypeError("Allocation view required")
        settings = AllocationParameters.from_json_values(game.config.world.parameters)
        action = Action(
            actor_id=game.actor_ids()[0],
            kind="allocate",
            payload={"allocation": list(project_simplex(settings.target, settings.budget))},
        )
        outcome = game.evaluate((action,))
        return SolveResult(
            status="solved",
            profile_domain="continuous",
            equilibria=(
                Equilibrium(actions=(action,), outcome=outcome, regrets={action.actor_id: 0.0}),
            ),
            diagnostics={"scope": "Single-actor vector optimum, not a general vector-game solver"},
        )
