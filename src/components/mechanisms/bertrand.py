"""Homogeneous-price competition: schemas, mechanism, and continuous solver view."""

from collections.abc import Sequence
from math import nextafter
from typing import Self

from pydantic import Field, model_validator

from components.common.economics.models import (
    ConstantMarginalCost,
    LinearDemand,
    LowestPriceAllocation,
    RevenueMinusCost,
)
from simulation_core.mechanism import Mechanism
from simulation_core.solver import BestResponseGameView, BestResponseResult
from simulation_core.types import (
    Action,
    FrozenModel,
    Outcome,
    SimulationConfig,
    TransitionResult,
    WorldConfig,
    WorldState,
)


class PricePayload(FrozenModel):
    price: float = Field(ge=0)


class PriceDomain(FrozenModel):
    lower: float = Field(default=0.0, ge=0)
    upper: float = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.lower >= self.upper:
            raise ValueError("Price domain must have lower < upper")
        return self

    def contains(self, price: float) -> bool:
        return self.lower <= price <= self.upper


class BertrandParameters(FrozenModel):
    demand: LinearDemand
    marginal_costs: dict[str, float]
    price_domain: PriceDomain
    action_kind: str = "set_price"
    history_field: str = "history"
    outcome_field: str = "market_outcome"

    @model_validator(mode="after")
    def valid_costs_and_fields(self) -> Self:
        for value in self.marginal_costs.values():
            ConstantMarginalCost(marginal_cost=value)
        if (
            not self.history_field
            or not self.outcome_field
            or self.history_field == self.outcome_field
        ):
            raise ValueError("State field names must be nonempty and distinct")
        return self


class HomogeneousBertrandMechanism(Mechanism):
    def __init__(self) -> None:
        self.allocation = LowestPriceAllocation()
        self.profit_model = RevenueMinusCost()

    def validate_config(self, config: WorldConfig) -> None:
        params = BertrandParameters.model_validate(config.parameters)
        ids = {actor.id for actor in config.actors}
        if len(ids) < 2 or set(params.marginal_costs) != ids:
            raise ValueError(
                "Bertrand requires at least two firms and exactly their marginal costs"
            )
        if any(params.action_kind not in actor.action_space.schemas for actor in config.actors):
            raise ValueError("Each firm must declare the configured pricing action")

    def validate_actions(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> None:
        params = BertrandParameters.model_validate(config.parameters)
        ids = [action.actor_id for action in actions]
        if len(ids) != len(config.actors) or set(ids) != set(params.marginal_costs):
            raise ValueError("Expected one price per configured firm")
        for action in actions:
            if action.kind != params.action_kind:
                raise ValueError("Invalid pricing action kind")
            price = PricePayload.model_validate(action.payload).price
            if not params.price_domain.contains(price):
                raise ValueError("Price outside declared feasible domain")

    def evaluate(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> Outcome:
        self.validate_actions(config, state, actions)
        params = BertrandParameters.model_validate(config.parameters)
        prices = {
            action.actor_id: PricePayload.model_validate(action.payload).price for action in actions
        }
        allocation = self.allocation.allocate(prices, params.demand)
        profits = {
            aid: self.profit_model.profit(
                price,
                allocation.quantities[aid],
                ConstantMarginalCost(marginal_cost=params.marginal_costs[aid]),
            )
            for aid, price in prices.items()
        }
        return Outcome(
            payoffs=profits,
            metrics={
                "prices": {aid: price for aid, price in prices.items()},
                "market_price": allocation.market_price,
                "quantities": {aid: quantity for aid, quantity in allocation.quantities.items()},
                "total_quantity": allocation.total_quantity,
                "revenues": {aid: prices[aid] * allocation.quantities[aid] for aid in prices},
            },
        )

    def transition(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> TransitionResult:
        outcome = self.evaluate(config, state, actions)
        params = BertrandParameters.model_validate(config.parameters)
        history = state.public.get(params.history_field, [])
        if not isinstance(history, list):
            raise TypeError("Pricing history must be a list")
        public = dict(state.public)
        public[params.history_field] = [*history, {a.actor_id: a.payload["price"] for a in actions}]
        public[params.outcome_field] = outcome.model_dump(mode="json")
        return TransitionResult(public=public, outcome=outcome)

    def validate_state(self, config: WorldConfig, state: WorldState) -> None:
        params = BertrandParameters.model_validate(config.parameters)
        history = state.public.get(params.history_field, [])
        if not isinstance(history, list) or len(history) != state.tick:
            raise ValueError("History must contain one price profile per committed tick")
        for profile in history:
            if not isinstance(profile, dict) or set(profile) != set(params.marginal_costs):
                raise ValueError("Invalid stored price profile")
            for price in profile.values():
                if isinstance(price, bool) or not isinstance(price, (int, float)):
                    raise TypeError("Stored prices must be numeric")
                if not params.price_domain.contains(float(price)):
                    raise ValueError("Stored price outside domain")
        if state.tick:
            last = history[-1]
            if not isinstance(last, dict):
                raise TypeError("Invalid price history")
            actions = tuple(
                Action(actor_id=aid, kind=params.action_kind, payload={"price": price})
                for aid, price in last.items()
            )
            expected = self.evaluate(config, state, actions).model_dump(mode="json")
            if state.public.get(params.outcome_field) != expected:
                raise ValueError("Stored market outcome disagrees with committed prices")


class BertrandGameView(BestResponseGameView):
    def __init__(self, config: SimulationConfig, state: WorldState, mechanism: Mechanism) -> None:
        if not isinstance(mechanism, HomogeneousBertrandMechanism):
            raise TypeError("Bertrand view requires the homogeneous Bertrand mechanism")
        self.config = config.model_copy(deep=True)
        self.state = state.model_copy(deep=True)
        self.mechanism = mechanism
        mechanism.validate_config(self.config.world.model_copy(deep=True))
        self.parameters = BertrandParameters.model_validate(self.config.world.parameters)

    def actor_ids(self) -> tuple[str, ...]:
        return tuple(actor.id for actor in self.config.world.actors)

    def price_action(self, actor_id: str, price: float) -> Action:
        return Action(actor_id=actor_id, kind=self.parameters.action_kind, payload={"price": price})

    def evaluate(self, profile: Sequence[Action]) -> Outcome:
        return self.mechanism.evaluate(
            self.config.world.model_copy(deep=True),
            self.state.model_copy(deep=True),
            tuple(a.model_copy(deep=True) for a in profile),
        )

    def best_response(self, actor_id: str, profile: Sequence[Action]) -> BestResponseResult:
        baseline = self.evaluate(profile)
        prices = {
            action.actor_id: PricePayload.model_validate(action.payload).price for action in profile
        }
        if actor_id not in prices:
            raise ValueError("Actor absent from profile")
        params = self.parameters
        low, high = params.price_domain.lower, params.price_domain.upper
        rival = min(price for aid, price in prices.items() if aid != actor_id)
        cost = params.marginal_costs[actor_id]
        # Stationary point of linear-demand monopoly profit, clipped to the feasible domain.
        stationary = params.demand.choke_price / 2 + cost / 2
        candidates = {low, high}
        if low <= rival <= high:
            candidates.add(rival)  # exact tie is its own discontinuous branch
        undercut_ceiling = min(high, rival)
        if low < rival:
            optimum = min(max(stationary, low), undercut_ceiling)
            if optimum < rival:
                candidates.add(optimum)
            if low <= params.demand.choke_price < rival and params.demand.choke_price <= high:
                candidates.add(params.demand.choke_price)

        def payoff(price: float) -> float:
            actions = tuple(
                self.price_action(aid, price if aid == actor_id else prices[aid])
                for aid in self.actor_ids()
            )
            return self.evaluate(actions).payoffs[actor_id]

        best_price = max(sorted(candidates), key=payoff)
        best_payoff = payoff(best_price)
        attained = True
        supremum = best_payoff
        witness_price = best_price
        # An increasing undercut branch may have a supremum at the excluded rival price.
        # Reuse the mechanism's demand/cost/profit primitives for that branch's limit.
        if low < rival <= high and stationary >= rival:
            limit = self.mechanism.profit_model.profit(
                rival, params.demand.quantity(rival), ConstantMarginalCost(marginal_cost=cost)
            )
            if limit > 0 and limit >= best_payoff:
                supremum = limit
                attained = False
                witness_price = nextafter(rival, low)
        current = baseline.payoffs[actor_id]
        return BestResponseResult(
            actor_id=actor_id,
            current_payoff=current,
            supremum_payoff=supremum,
            gain=max(0.0, supremum - current),
            attained=attained,
            maximizing_action=self.price_action(actor_id, best_price) if attained else None,
            witness_action=self.price_action(actor_id, witness_price),
            witness_payoff=payoff(witness_price),
        )
