"""Sealed-bid second-price (Vickrey) auction mechanism."""

from collections.abc import Sequence
from math import isfinite
from typing import Literal, Self

from experiment_extension.schemas import BidPayload
from pydantic import BaseModel, Field, JsonValue, model_validator

from simulation_core.mechanism import Mechanism
from simulation_core.types import (
    Action,
    FrozenModel,
    Outcome,
    TransitionResult,
    WorldConfig,
    WorldState,
)


class AuctionParameters(FrozenModel):
    """Validated world parameters for the second-price auction."""

    action_kind: str = Field(min_length=1)
    bids_field: str = Field(min_length=1)
    outcome_field: str = Field(min_length=1)
    tie_break: Literal["configuration_order"] = "configuration_order"

    @model_validator(mode="after")
    def _distinct_history_fields(self) -> Self:
        if self.bids_field == self.outcome_field:
            raise ValueError("Bid and outcome history fields must be distinct")
        return self


def _finite_number(value: JsonValue, *, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{what} must be a number")  # noqa: TRY004
    amount = float(value)
    if not isfinite(amount):
        raise ValueError(f"{what} must be finite")
    return amount


def _bid_amount(value: JsonValue, *, what: str) -> float:
    amount = _finite_number(value, what=what)
    if amount < 0:
        raise ValueError(f"{what} must be nonnegative")
    return amount


def _settle(bids: dict[str, float], order: Sequence[str]) -> tuple[str, float]:
    """Winner under the configuration-order tie-break and the second-highest bid."""
    if len(order) < 2:
        raise ValueError("Second-price settlement requires at least two bidders")
    winner = max(order, key=lambda aid: bids[aid])
    payment = sorted(bids.values(), reverse=True)[1]
    return winner, payment


class SecondPriceAuctionMechanism(Mechanism):
    """One-round sealed-bid second-price settlement with quasi-linear payoffs."""

    requires_joint_actions = True

    def required_action_schemas(self, config: WorldConfig) -> dict[str, dict[str, type[BaseModel]]]:
        params = AuctionParameters.model_validate(config.parameters)
        return {actor.id: {params.action_kind: BidPayload} for actor in config.actors}

    def validate_config(self, config: WorldConfig) -> None:
        params = AuctionParameters.model_validate(config.parameters)
        if len(config.actors) < 2:
            raise ValueError("Second-price auction requires at least two bidders")
        for actor in config.actors:
            if params.action_kind not in actor.action_space.schemas:
                raise ValueError(f"Bidder {actor.id} must declare a {params.action_kind!r} action")
        for actor in config.actors:
            private = config.initial_private_state.get(actor.id)
            if private is None or "valuation" not in private.facts:
                raise ValueError(f"Missing private valuation for bidder {actor.id}")
            _finite_number(private.facts["valuation"], what=f"Valuation for {actor.id}")

    def validate_state(self, config: WorldConfig, state: WorldState) -> None:
        params = AuctionParameters.model_validate(config.parameters)
        order = [actor.id for actor in config.actors]
        bids_history = state.public.get(params.bids_field, [])
        outcome_history = state.public.get(params.outcome_field, [])
        if not isinstance(bids_history, list) or len(bids_history) != state.tick:
            raise ValueError("Bid history must contain one profile per committed tick")
        if not isinstance(outcome_history, list) or len(outcome_history) != state.tick:
            raise ValueError("Outcome history must contain one record per committed tick")
        for profile, record in zip(bids_history, outcome_history):
            if not isinstance(profile, dict) or set(profile) != set(order):
                raise ValueError("Stored bid profile must cover every bidder exactly once")
            bids = {aid: _bid_amount(profile[aid], what=f"Stored bid for {aid}") for aid in order}
            if (
                not isinstance(record, dict)
                or set(record) != {"winner", "payment"}
                or record["winner"] not in order
            ):
                raise ValueError("Stored auction record must name the winner and payment")
            payment = _bid_amount(record["payment"], what="Stored auction payment")
            winner, expected_payment = _settle(bids, order)
            if record["winner"] != winner or payment != expected_payment:
                raise ValueError("Stored auction outcome disagrees with the committed bids")

    def validate_actions(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> None:
        params = AuctionParameters.model_validate(config.parameters)
        expected = [actor.id for actor in config.actors]
        submitted = [action.actor_id for action in actions]
        if len(submitted) != len(expected) or set(submitted) != set(expected):
            raise ValueError("Expected exactly one sealed bid per bidder")
        for action in actions:
            if action.kind != params.action_kind:
                raise ValueError(
                    f"Unknown action kind {action.kind!r} for bidder {action.actor_id}"
                )
            BidPayload.model_validate(action.payload)

    def evaluate(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> Outcome:
        self.validate_actions(config, state, actions)
        order = [actor.id for actor in config.actors]
        bids = {
            action.actor_id: BidPayload.model_validate(action.payload).bid for action in actions
        }
        valuations: dict[str, float] = {}
        for aid in order:
            private = state.private.get(aid)
            if private is None or "valuation" not in private.facts:
                raise ValueError(f"Missing private valuation for bidder {aid}")
            valuations[aid] = _finite_number(
                private.facts["valuation"], what=f"Valuation for {aid}"
            )
        winner, payment = _settle(bids, order)
        payoffs = {aid: (valuations[aid] - payment if aid == winner else 0.0) for aid in order}
        recorded_bids: dict[str, JsonValue] = {aid: bids[aid] for aid in order}
        return Outcome(
            payoffs=payoffs,
            metrics={"winner": winner, "payment": payment, "bids": recorded_bids},
        )

    def transition(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> TransitionResult:
        params = AuctionParameters.model_validate(config.parameters)
        outcome = self.evaluate(config, state, actions)
        bids_history = state.public.get(params.bids_field, [])
        outcome_history = state.public.get(params.outcome_field, [])
        if not isinstance(bids_history, list) or not isinstance(outcome_history, list):
            raise TypeError("Auction history fields must be lists")
        public = dict(state.public)
        bid_profile: dict[str, JsonValue] = {
            action.actor_id: BidPayload.model_validate(action.payload).bid for action in actions
        }
        record: dict[str, JsonValue] = {
            "winner": outcome.metrics["winner"],
            "payment": outcome.metrics["payment"],
        }
        updated_bids: list[JsonValue] = [*bids_history, bid_profile]
        updated_outcomes: list[JsonValue] = [*outcome_history, record]
        public[params.bids_field] = updated_bids
        public[params.outcome_field] = updated_outcomes
        return TransitionResult(public=public, outcome=outcome)
