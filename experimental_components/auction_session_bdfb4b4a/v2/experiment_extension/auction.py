"""Sealed-bid second-price auction mechanism, schemas, and truthful reference."""

from collections.abc import Sequence
from math import isfinite
from typing import Literal

from pydantic import BaseModel, Field, JsonValue, field_validator

from simulation_core.mechanism import Mechanism
from simulation_core.types import (
    Action,
    FrozenModel,
    Outcome,
    PrivateState,
    TransitionResult,
    WorldConfig,
    WorldState,
)


class BidPayload(FrozenModel):
    bid: float = Field(ge=0)


class AuctionParameters(FrozenModel):
    action_kind: str = Field(default="submit_bid", min_length=1)
    valuation_field: str = Field(default="valuation", min_length=1)
    rules_field: str = Field(default="auction_rules", min_length=1)
    history_field: str = Field(default="bid_history", min_length=1)
    outcome_field: str = Field(default="auction_outcome", min_length=1)
    value_model: Literal["independent_private_values"] = "independent_private_values"
    utility_model: Literal["quasi_linear"] = "quasi_linear"
    reserve_price: float = 0.0
    budget_constraints: Literal["none"] = "none"
    tie_break: Literal["configuration_order"] = "configuration_order"

    @field_validator("reserve_price")
    @classmethod
    def _no_reserve(cls, value: float) -> float:
        if value != 0.0:
            raise ValueError("Only a zero reserve price is supported")
        return value


class TruthfulReference(FrozenModel):
    bids: dict[str, float]
    winner: str
    payment: float
    payoffs: dict[str, float]


def _ranked(bids: dict[str, float], order: tuple[str, ...]) -> tuple[str, float]:
    winner = min(order, key=lambda actor: (-bids[actor], order.index(actor)))
    payment = sorted(bids.values(), reverse=True)[1]
    return winner, payment


def truthful_reference(valuations: dict[str, float], order: tuple[str, ...]) -> TruthfulReference:
    if set(order) != set(valuations) or len(order) != len(valuations):
        raise ValueError("Order must list exactly the valued bidders once each")
    if len(order) < 2:
        raise ValueError("A second price needs at least two bidders")
    for actor, value in valuations.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            or value < 0
        ):
            raise ValueError(f"Invalid valuation for {actor}")
    bids = {actor: float(valuations[actor]) for actor in order}
    winner, payment = _ranked(bids, order)
    return TruthfulReference(
        bids=bids,
        winner=winner,
        payment=payment,
        payoffs={actor: (bids[actor] - payment if actor == winner else 0.0) for actor in order},
    )


class SecondPriceAuctionMechanism(Mechanism):
    requires_joint_actions = True

    def required_action_schemas(self, config: WorldConfig) -> dict[str, dict[str, type[BaseModel]]]:
        params = AuctionParameters.model_validate(config.parameters)
        return {actor.id: {params.action_kind: BidPayload} for actor in config.actors}

    def validate_config(self, config: WorldConfig) -> None:
        params = AuctionParameters.model_validate(config.parameters)
        self._validate_facts(config, config.initial_private_state, params.valuation_field)
        if params.rules_field not in config.initial_public_state:
            raise ValueError("Missing configured public rules field")
        if len(config.actors) < 2:
            raise ValueError("A second-price auction needs at least two bidders")

    @staticmethod
    def _validate_facts(config: WorldConfig, private: dict[str, PrivateState], field: str) -> None:
        for actor in config.actors:
            own = private.get(actor.id)
            value = None if own is None else own.facts.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value < 0
            ):
                raise ValueError(f"Invalid initial/state valuation for {actor.id}")

    def validate_state(self, config: WorldConfig, state: WorldState) -> None:
        params = AuctionParameters.model_validate(config.parameters)
        self._validate_facts(config, state.private, params.valuation_field)
        if params.rules_field not in state.public:
            raise ValueError("Missing configured public rules field")
        history = state.public.get(params.history_field, [])
        if not isinstance(history, list) or len(history) != state.tick:
            raise ValueError("Bid history must contain one batch per committed tick")
        known = {actor.id for actor in config.actors}
        for batch in history:
            if not isinstance(batch, dict):
                raise TypeError("Each history batch must map bidders to bids")
            for actor_id, bid in batch.items():
                if (
                    actor_id not in known
                    or isinstance(bid, bool)
                    or not isinstance(bid, (int, float))
                    or not isfinite(bid)
                    or bid < 0
                ):
                    raise ValueError("Invalid recorded bid")
        outcome = state.public.get(params.outcome_field)
        if outcome is None:
            return
        if not isinstance(outcome, dict):
            raise TypeError("Invalid recorded auction outcome")
        winner = outcome.get("winner")
        payment = outcome.get("payment")
        payoffs = outcome.get("payoffs")
        if not isinstance(winner, str) or winner not in known:
            raise ValueError("Invalid recorded auction winner")
        if (
            isinstance(payment, bool)
            or not isinstance(payment, (int, float))
            or not isfinite(payment)
            or payment < 0
        ):
            raise ValueError("Invalid recorded auction payment")
        if not isinstance(payoffs, dict):
            raise TypeError("Invalid recorded auction payoffs")

    def validate_actions(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> None:
        params = AuctionParameters.model_validate(config.parameters)
        expected = [actor.id for actor in config.actors]
        if len(actions) != len(expected) or {a.actor_id for a in actions} != set(expected):
            raise ValueError("Exactly one action required per bidder")
        for action in actions:
            if action.kind != params.action_kind:
                raise ValueError(f"Unknown action kind: {action.kind}")
            BidPayload.model_validate(action.payload)

    def _clearing(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> tuple[dict[str, float], dict[str, float], str, float]:
        params = AuctionParameters.model_validate(config.parameters)
        bids = {
            action.actor_id: BidPayload.model_validate(action.payload).bid for action in actions
        }
        order = tuple(actor.id for actor in config.actors)
        valuations: dict[str, float] = {}
        for actor_id in order:
            if actor_id not in state.private:
                raise ValueError(f"Missing private state for {actor_id}")
            value = state.private[actor_id].facts.get(params.valuation_field)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value < 0
            ):
                raise ValueError(f"Invalid valuation for {actor_id}")
            valuations[actor_id] = float(value)
        winner, payment = _ranked({actor_id: bids[actor_id] for actor_id in order}, order)
        payoffs = {
            actor_id: (valuations[actor_id] - payment if actor_id == winner else 0.0)
            for actor_id in order
        }
        return bids, payoffs, winner, payment

    def evaluate(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> Outcome:
        bids, payoffs, winner, payment = self._clearing(config, state, actions)
        return Outcome(
            payoffs=payoffs,
            metrics={"winner": winner, "payment": payment, "bids": dict(bids)},
        )

    def transition(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> TransitionResult:
        params = AuctionParameters.model_validate(config.parameters)
        outcome = self.evaluate(config, state, actions)
        bids = {
            action.actor_id: BidPayload.model_validate(action.payload).bid for action in actions
        }
        public = dict(state.public)
        raw_history = public.get(params.history_field, [])
        if not isinstance(raw_history, list):
            raise TypeError("Bid history must be a list of batches")
        batch: dict[str, JsonValue] = {actor_id: bid for actor_id, bid in bids.items()}
        history: list[JsonValue] = [*raw_history, batch]
        public[params.history_field] = history
        public[params.outcome_field] = {
            "winner": outcome.metrics["winner"],
            "payment": outcome.metrics["payment"],
            "payoffs": dict(outcome.payoffs),
        }
        return TransitionResult(public=public, outcome=outcome)
