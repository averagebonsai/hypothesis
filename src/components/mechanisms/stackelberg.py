"""Quantity commitments, market clearing, and a read-only two-stage game view."""

from collections.abc import Iterable, Sequence
from itertools import islice
from math import isfinite
from typing import Self

from pydantic import BaseModel, Field, JsonValue, model_validator

from components.common.economics.models import (
    ConstantMarginalCost,
    LinearInverseDemand,
    RevenueMinusCost,
)
from simulation_core.domains import ScalarInterval
from simulation_core.game_view import MechanismGameView
from simulation_core.mechanism import Mechanism
from simulation_core.protocol import DecisionPhase
from simulation_core.solver import TwoStageGameView
from simulation_core.types import (
    Action,
    FrozenModel,
    Outcome,
    SimulationConfig,
    TransitionResult,
    WorldConfig,
    WorldState,
)


class QuantityPayload(FrozenModel):
    quantity: float = Field(ge=0)


class QuantityDomain(ScalarInterval):
    lower: float = Field(default=0.0, ge=0)
    upper: float = Field(gt=0)


class StackelbergParameters(FrozenModel):
    demand: LinearInverseDemand
    leader_id: str = Field(min_length=1)
    follower_id: str = Field(min_length=1)
    marginal_costs: dict[str, float]
    quantity_domains: dict[str, QuantityDomain]
    action_kind: str = "set_quantity"
    commitments_field: str = Field(default="commitments", min_length=1)
    history_field: str = Field(default="history", min_length=1)
    outcome_field: str = Field(default="market_outcome", min_length=1)

    @model_validator(mode="after")
    def references(self) -> Self:
        ids = {self.leader_id, self.follower_id}
        if len(ids) != 2 or set(self.marginal_costs) != ids or set(self.quantity_domains) != ids:
            raise ValueError(
                "Roles must be distinct and costs/domains must cover exactly both firms"
            )
        for cost in self.marginal_costs.values():
            ConstantMarginalCost(marginal_cost=cost)
        if len({self.commitments_field, self.history_field, self.outcome_field}) != 3:
            raise ValueError("State output field names must differ")
        if not isfinite(sum(domain.upper for domain in self.quantity_domains.values())):
            raise ValueError("Maximum total quantity must be finite")
        return self


class StackelbergMechanism(Mechanism):
    def required_action_schemas(self, config: WorldConfig) -> dict[str, dict[str, type[BaseModel]]]:
        params = StackelbergParameters.from_json_values(config.parameters)
        return {actor.id: {params.action_kind: QuantityPayload} for actor in config.actors}

    def validate_schedule(
        self, config: WorldConfig, stages: Iterable[DecisionPhase] | None
    ) -> None:
        params = self.parameters(config)
        if stages is not None and tuple(stage.actor_ids for stage in islice(stages, 3)) != (
            (params.leader_id,),
            (params.follower_id,),
        ):
            raise ValueError(
                "Stackelberg requires exactly a leader stage followed by a follower stage"
            )

    def __init__(self) -> None:
        self.profit = RevenueMinusCost()

    def parameters(self, config: WorldConfig) -> StackelbergParameters:
        return StackelbergParameters.from_json_values(config.parameters)

    def validate_config(self, config: WorldConfig) -> None:
        params = self.parameters(config)
        if {actor.id for actor in config.actors} != {params.leader_id, params.follower_id} or len(
            config.actors
        ) != 2:
            raise ValueError("Stackelberg market requires exactly its leader and follower")
        if any(params.action_kind not in actor.action_space.schemas for actor in config.actors):
            raise ValueError("Each firm must declare its quantity action")

    def _quantity(self, params: StackelbergParameters, action: Action) -> float:
        if action.actor_id not in params.quantity_domains or action.kind != params.action_kind:
            raise ValueError("Invalid quantity action identity or kind")
        quantity = QuantityPayload.model_validate(action.payload).quantity
        if not params.quantity_domains[action.actor_id].contains(quantity):
            raise ValueError("Quantity outside declared domain")
        return quantity

    def _commitments(self, params: StackelbergParameters, state: WorldState) -> dict[str, float]:
        raw = state.public.get(params.commitments_field, {})
        if not isinstance(raw, dict):
            raise TypeError("Commitments must be an object")
        return {
            aid: self._quantity(
                params, Action(actor_id=aid, kind=params.action_kind, payload={"quantity": value})
            )
            for aid, value in raw.items()
        }

    def validate_actions(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> None:
        params = self.parameters(config)
        committed = self._commitments(params, state)
        if not committed:
            expected = params.leader_id
        elif set(committed) == {params.leader_id}:
            expected = params.follower_id
        else:
            raise ValueError("Market already complete or commitments are out of order")
        if len(actions) != 1 or actions[0].actor_id != expected:
            raise ValueError("Quantity commitments must be leader then follower, once each")
        self._quantity(params, actions[0])

    def evaluate(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> Outcome:
        # Complete hypothetical profiles are independent of previously committed choices.
        params = self.parameters(config)
        if len(actions) != 2 or {a.actor_id for a in actions} != {
            params.leader_id,
            params.follower_id,
        }:
            raise ValueError("Evaluation requires a complete joint quantity profile")
        quantities = {a.actor_id: self._quantity(params, a) for a in actions}
        total = sum(quantities.values())
        price = params.demand.price(total)
        payoffs = {
            aid: self.profit.profit(
                price, q, ConstantMarginalCost(marginal_cost=params.marginal_costs[aid])
            )
            for aid, q in quantities.items()
        }
        return Outcome(
            payoffs=payoffs,
            metrics={
                "price": price,
                "total_quantity": total,
                "quantities": {aid: q for aid, q in quantities.items()},
                "revenues": {aid: price * q for aid, q in quantities.items()},
                "market_complete": True,
            },
        )

    def transition(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> TransitionResult:
        self.validate_actions(config, state, actions)
        params = self.parameters(config)
        commitments = self._commitments(params, state)
        commitments[actions[0].actor_id] = self._quantity(params, actions[0])
        history = state.public.get(params.history_field, [])
        if not isinstance(history, list):
            raise TypeError("Commitment history must be a list")
        public: dict[str, JsonValue] = {
            **state.public,
            params.commitments_field: {aid: q for aid, q in commitments.items()},
            params.history_field: [
                *history,
                {actions[0].actor_id: commitments[actions[0].actor_id]},
            ],
        }
        if len(commitments) == 2:
            joint = tuple(
                Action(
                    actor_id=aid, kind=params.action_kind, payload={"quantity": commitments[aid]}
                )
                for aid in (params.leader_id, params.follower_id)
            )
            outcome = self.evaluate(config, state, joint)
            public[params.outcome_field] = outcome.model_dump(mode="json")
        else:
            # Committing the leader action is not a realized market payoff.
            outcome = Outcome(
                metrics={
                    "market_complete": False,
                    "committed_quantities": {aid: q for aid, q in commitments.items()},
                }
            )
        return TransitionResult(public=public, outcome=outcome)

    def validate_state(self, config: WorldConfig, state: WorldState) -> None:
        params = self.parameters(config)
        history = state.public.get(params.history_field, [])
        if not isinstance(history, list) or len(history) != state.tick or state.tick > 2:
            raise ValueError("State must contain one commitment per stage of a single episode")
        expected = {}
        for index, item in enumerate(history):
            aid = (params.leader_id, params.follower_id)[index]
            if not isinstance(item, dict) or set(item) != {aid}:
                raise ValueError("Stored commitments must follow leader/follower order")
            expected[aid] = self._quantity(
                params,
                Action(actor_id=aid, kind=params.action_kind, payload={"quantity": item[aid]}),
            )
        if self._commitments(params, state) != expected:
            raise ValueError("Commitments disagree with canonical stage history")
        if state.tick < 2:
            if params.outcome_field in state.public:
                raise ValueError("A final market outcome cannot exist before the follower commits")
        else:
            joint = tuple(
                Action(actor_id=aid, kind=params.action_kind, payload={"quantity": q})
                for aid, q in expected.items()
            )
            if state.public.get(params.outcome_field) != self.evaluate(
                config, state, joint
            ).model_dump(mode="json"):
                raise ValueError("Market outcome disagrees with committed quantities")


class StackelbergGameView(MechanismGameView, TwoStageGameView):
    mechanism: StackelbergMechanism

    def __init__(self, config: SimulationConfig, state: WorldState, mechanism: Mechanism) -> None:
        if not isinstance(mechanism, StackelbergMechanism):
            raise TypeError("Stackelberg view requires its quantity-commitment mechanism")
        super().__init__(config, state, mechanism)
        self.parameters = mechanism.parameters(self.config.world)

    def leader_id(self) -> str:
        return self.parameters.leader_id

    def follower_id(self) -> str:
        return self.parameters.follower_id

    def actor_ids(self) -> tuple[str, ...]:
        return (self.leader_id(), self.follower_id())

    def quantity_action(self, actor_id: str, quantity: float) -> Action:
        return Action(
            actor_id=actor_id, kind=self.parameters.action_kind, payload={"quantity": quantity}
        )

    def follower_response(self, leader_action: Action) -> Action:
        params = self.parameters
        if leader_action.actor_id != self.leader_id():
            raise ValueError("Expected the leader's commitment")
        quantity = self.mechanism._quantity(params, leader_action)
        domain = params.quantity_domains[self.follower_id()]
        raw = (
            params.demand.choke_quantity
            - params.marginal_costs[self.follower_id()] / params.demand.b
            - quantity
        ) / 2
        chosen = min(max(raw, domain.lower), domain.upper)
        return self.quantity_action(self.follower_id(), chosen)
