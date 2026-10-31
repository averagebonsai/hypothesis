"""Differentiated-price schemas, economic mechanism, and numerical solver view."""

from collections.abc import Sequence
from typing import Self

from pydantic import Field, model_validator

from components.common.economics.models import ConstantMarginalCost, RevenueMinusCost
from components.common.economics.segmented_logit import SegmentedLogitDemand
from components.common.math.scalar import ScalarSearchSettings, maximize_scalar
from components.mechanisms.bertrand import PriceDomain, PricePayload
from simulation_core.mechanism import Mechanism
from simulation_core.solver import BestResponseResult, DifferentiableScalarGameView
from simulation_core.types import (
    Action,
    FrozenModel,
    Outcome,
    SimulationConfig,
    TransitionResult,
    WorldConfig,
    WorldState,
)


class DifferentiatedBertrandParameters(FrozenModel):
    demand: SegmentedLogitDemand
    marginal_costs: dict[str, float]
    price_domains: dict[str, PriceDomain]
    action_kind: str = "set_price"
    history_field: str = Field(default="history", min_length=1)
    outcome_field: str = Field(default="market_outcome", min_length=1)

    @model_validator(mode="after")
    def dimensions(self) -> Self:
        ids = set(self.demand.firm_ids)
        if set(self.marginal_costs) != ids or set(self.price_domains) != ids:
            raise ValueError("Costs and price domains must cover exactly the demand firms")
        for cost in self.marginal_costs.values():
            ConstantMarginalCost(marginal_cost=cost)
        if self.history_field == self.outcome_field:
            raise ValueError("Output field names must differ")
        return self


class DifferentiatedBertrandMechanism(Mechanism):
    def __init__(self) -> None:
        self.profit = RevenueMinusCost()
        self._cached_parameters: DifferentiatedBertrandParameters | None = None

    def parameters(self, config: WorldConfig) -> DifferentiatedBertrandParameters:
        # Only immutable parsed input is cached, never outcomes, random draws or mutable state.
        if (
            self._cached_parameters is None
            or self._cached_parameters.model_dump(mode="json") != config.parameters
        ):
            self._cached_parameters = DifferentiatedBertrandParameters.from_json_values(
                config.parameters
            )
        return self._cached_parameters.model_copy(deep=True)

    def validate_config(self, config: WorldConfig) -> None:
        params = self.parameters(config)
        if len(config.actors) < 2 or set(params.demand.firm_ids) != {
            actor.id for actor in config.actors
        }:
            raise ValueError(
                "Differentiated Bertrand needs at least two firms with matching demand IDs"
            )
        if any(params.action_kind not in actor.action_space.schemas for actor in config.actors):
            raise ValueError("Every firm must declare the pricing action")

    def prices(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> dict[str, float]:
        params = self.parameters(config)
        if len(actions) != len(config.actors) or {a.actor_id for a in actions} != set(
            params.demand.firm_ids
        ):
            raise ValueError("Exactly one price per firm is required")
        result = {}
        for action in actions:
            if action.kind != params.action_kind:
                raise ValueError("Invalid pricing action kind")
            value = PricePayload.model_validate(action.payload).price
            if not params.price_domains[action.actor_id].contains(value):
                raise ValueError("Price outside declared firm bounds")
            result[action.actor_id] = value
        return result

    def validate_actions(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> None:
        self.prices(config, state, actions)

    def evaluate(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> Outcome:
        prices = self.prices(config, state, actions)
        params = self.parameters(config)
        demand = params.demand.evaluate(prices)
        return Outcome(
            payoffs={
                aid: self.profit.profit(
                    price,
                    demand.quantities[aid],
                    ConstantMarginalCost(marginal_cost=params.marginal_costs[aid]),
                )
                for aid, price in prices.items()
            },
            metrics={
                **demand.model_dump(mode="json"),
                "prices": {aid: p for aid, p in prices.items()},
                "total_quantity": sum(demand.quantities.values()),
            },
        )

    def own_profit_gradient(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> dict[str, float]:
        prices = self.prices(config, state, actions)
        params = self.parameters(config)
        demand = params.demand.evaluate(prices)
        derivatives = params.demand.own_price_derivatives(prices)
        return {
            aid: demand.quantities[aid] + (price - params.marginal_costs[aid]) * derivatives[aid]
            for aid, price in prices.items()
        }

    def transition(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> TransitionResult:
        outcome = self.evaluate(config, state, actions)
        params = self.parameters(config)
        history = state.public.get(params.history_field, [])
        if not isinstance(history, list):
            raise TypeError("Price history must be a list")
        return TransitionResult(
            public={
                **state.public,
                params.history_field: [*history, {a.actor_id: a.payload["price"] for a in actions}],
                params.outcome_field: outcome.model_dump(mode="json"),
            },
            outcome=outcome,
        )

    def validate_state(self, config: WorldConfig, state: WorldState) -> None:
        params = self.parameters(config)
        history = state.public.get(params.history_field, [])
        if not isinstance(history, list) or len(history) != state.tick:
            raise ValueError("History must have one profile per committed tick")
        for item in history:
            if not isinstance(item, dict):
                raise TypeError("History profiles must be objects")
            actions = tuple(
                Action(actor_id=aid, kind=params.action_kind, payload={"price": price})
                for aid, price in item.items()
            )
            self.validate_actions(config, state, actions)
        if state.tick:
            item = history[-1]
            if not isinstance(item, dict):
                raise TypeError("Invalid history")
            actions = tuple(
                Action(actor_id=aid, kind=params.action_kind, payload={"price": p})
                for aid, p in item.items()
            )
            if state.public.get(params.outcome_field) != self.evaluate(
                config, state, actions
            ).model_dump(mode="json"):
                raise ValueError("Stored outcome disagrees with committed prices")


class DifferentiatedBertrandGameView(DifferentiableScalarGameView):
    def __init__(self, config: SimulationConfig, state: WorldState, mechanism: Mechanism) -> None:
        if not isinstance(mechanism, DifferentiatedBertrandMechanism):
            raise TypeError("Differentiated pricing view requires its corresponding mechanism")
        self.config = config.model_copy(deep=True)
        self.state = state.model_copy(deep=True)
        self.mechanism = mechanism
        self.mechanism.validate_config(self.config.world)
        self.parameters = self.mechanism.parameters(self.config.world)

    def actor_ids(self) -> tuple[str, ...]:
        return tuple(actor.id for actor in self.config.world.actors)

    def action_bounds(self, actor_id: str) -> tuple[float, float]:
        domain = self.parameters.price_domains[actor_id]
        return domain.lower, domain.upper

    def scalar_action(self, actor_id: str, value: float) -> Action:
        return Action(actor_id=actor_id, kind=self.parameters.action_kind, payload={"price": value})

    def action_value(self, action: Action) -> float:
        return PricePayload.model_validate(action.payload).price

    def evaluate(self, profile: Sequence[Action]) -> Outcome:
        return self.mechanism.evaluate(
            self.config.world.model_copy(deep=True),
            self.state.model_copy(deep=True),
            tuple(action.model_copy(deep=True) for action in profile),
        )

    def own_payoff_gradient(self, profile: Sequence[Action]) -> dict[str, float]:
        return self.mechanism.own_profit_gradient(
            self.config.world.model_copy(deep=True),
            self.state.model_copy(deep=True),
            tuple(action.model_copy(deep=True) for action in profile),
        )

    def payoff_scale(self) -> float:
        return sum(segment.population for segment in self.parameters.demand.segments)

    def best_response(self, actor_id: str, profile: Sequence[Action]) -> BestResponseResult:
        baseline = self.evaluate(profile)
        actions = {a.actor_id: a for a in profile}

        def objective(value: float) -> float:
            candidate = tuple(
                self.scalar_action(aid, value) if aid == actor_id else actions[aid]
                for aid in self.actor_ids()
            )
            return self.evaluate(candidate).payoffs[actor_id]

        result = maximize_scalar(
            objective,
            self.action_bounds(actor_id),
            ScalarSearchSettings(),
            self.action_value(actions[actor_id]),
        )
        action = self.scalar_action(actor_id, result.value)
        current = baseline.payoffs[actor_id]
        return BestResponseResult(
            actor_id=actor_id,
            current_payoff=current,
            supremum_payoff=result.payoff,
            gain=max(0.0, result.payoff - current),
            attained=True,
            maximizing_action=action,
            witness_action=action,
            witness_payoff=result.payoff,
            certification="numerical",
            diagnostics={
                **result.model_dump(mode="json"),
                "qualification": "Best-found numerical payoff; no rigorous global-optimality certificate",
            },
        )
