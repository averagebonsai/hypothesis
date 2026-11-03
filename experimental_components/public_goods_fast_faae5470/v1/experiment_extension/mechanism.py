"""Withdrawal/budget settlement for the repeated public-goods game.

Rules (all values native typed data, never JSON-encoded strings):
  available_i = saved_balance_i + endowment_this_round
  payoff_i = endowment_this_round - contribution_i + multiplier * sum(contributions) / N
  closing_i = opening_i + payoff_i
Round number is tick + 1. Rounds up to ``endowed_rounds`` pay ``endowment``;
later rounds pay zero while saved balances remain spendable. Any finite
nonnegative contribution up to available funds is legal.

Saved balances and the round history live in public state, matching the
required full public feedback (contributions and payoffs are inferable by all
anyway). The mechanism therefore returns no private updates, leaving each
policy free to update its own memory without runtime conflicts.
"""

from collections.abc import Sequence
from math import isfinite

from pydantic import BaseModel, Field, JsonValue

from simulation_core.mechanism import Mechanism
from simulation_core.types import (
    Action,
    FrozenModel,
    Outcome,
    TransitionResult,
    WorldConfig,
    WorldState,
)

ACTION_KIND = "contribute"


class ContributionPayload(FrozenModel):
    contribution: float


class PublicGoodsParameters(FrozenModel):
    participant_count: int = Field(gt=0)
    rounds: int = Field(gt=0)
    endowed_rounds: int = Field(ge=0)
    endowment: float = Field(ge=0.0)
    multiplier: float = Field(gt=0.0)


def _params(config: WorldConfig) -> PublicGoodsParameters:
    params = PublicGoodsParameters.model_validate(config.parameters)
    if params.endowed_rounds > params.rounds:
        raise ValueError("endowed_rounds cannot exceed rounds")
    if params.participant_count != len(config.actors):
        raise ValueError("participant_count must match the configured actors")
    return params


def _balances(config: WorldConfig, state: WorldState) -> dict[str, float]:
    raw = state.public.get("saved_balances")
    if not isinstance(raw, dict):
        raise TypeError("saved_balances must map each actor to a number")
    balances: dict[str, float] = {}
    for actor in config.actors:
        value = raw.get(actor.id)
        if not isinstance(value, (int, float)) or not isfinite(value):
            raise ValueError(f"Missing or nonfinite balance for {actor.id}")
        balances[actor.id] = float(value)
    return balances


def _round_endowment(params: PublicGoodsParameters, tick: int) -> float:
    return params.endowment if tick + 1 <= params.endowed_rounds else 0.0


class PublicGoodsWithdrawalMechanism(Mechanism):
    requires_joint_actions = True

    def validate_config(self, config: WorldConfig) -> None:
        _params(config)

    def validate_state(self, config: WorldConfig, state: WorldState) -> None:
        params = _params(config)
        _balances(config, state)
        history = state.public.get("history")
        if not isinstance(history, list) or len(history) != state.tick:
            raise ValueError("history must hold one record per committed tick")
        for key in ("rounds", "endowed_rounds", "endowment", "multiplier"):
            if state.public.get(key) != config.parameters[key]:
                raise ValueError(f"public field {key} differs from parameters")
        if params.participant_count != len(config.actors):
            raise ValueError("participant_count must match the configured actors")

    def required_action_schemas(self, config: WorldConfig) -> dict[str, dict[str, type[BaseModel]]]:
        return {actor.id: {ACTION_KIND: ContributionPayload} for actor in config.actors}

    def validate_actions(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> None:
        params = _params(config)
        balances = _balances(config, state)
        if len(actions) != len(config.actors) or {action.actor_id for action in actions} != set(
            balances
        ):
            raise ValueError("Exactly one action required per actor")
        endowment = _round_endowment(params, state.tick)
        for action in actions:
            if action.kind != ACTION_KIND:
                raise ValueError(f"Unknown action kind {action.kind}")
            payload = ContributionPayload.model_validate(action.payload)
            available = balances[action.actor_id] + endowment
            if payload.contribution < 0.0:
                raise ValueError("Contributions cannot be negative")
            if payload.contribution > available:
                raise ValueError("Contribution exceeds available funds")

    def evaluate(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> Outcome:
        params = _params(config)
        balances = _balances(config, state)
        by_actor = {action.actor_id: action for action in actions}
        contribs = {
            aid: ContributionPayload.model_validate(by_actor[aid].payload).contribution
            for aid in balances
        }
        total = sum(contribs.values())
        endowment = _round_endowment(params, state.tick)
        pool_each = params.multiplier * total / params.participant_count
        payoffs = {aid: endowment - contribs[aid] + pool_each for aid in balances}
        return Outcome(
            payoffs=payoffs,
            metrics={
                "round": state.tick + 1,
                "endowment": endowment,
                "total_contributions": total,
                "pool_per_actor": pool_each,
            },
        )

    def transition(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> TransitionResult:
        self.validate_actions(config, state, actions)
        params = _params(config)
        balances = _balances(config, state)
        outcome = self.evaluate(config, state, actions)
        new_balances = {aid: balances[aid] + outcome.payoffs[aid] for aid in balances}
        contribs = {
            action.actor_id: ContributionPayload.model_validate(action.payload).contribution
            for action in actions
        }
        public = dict(state.public)
        previous = public.get("history", [])
        if not isinstance(previous, list):
            raise TypeError("history must hold one record per committed tick")
        history: list[JsonValue] = list(previous)
        record: dict[str, JsonValue] = {
            "round": state.tick + 1,
            "endowment": _round_endowment(params, state.tick),
            "contributions": dict(contribs),
            "payoffs": dict(outcome.payoffs),
            "balances": dict(new_balances),
        }
        history.append(record)
        public["history"] = history
        saved: dict[str, JsonValue] = dict(new_balances)
        public["saved_balances"] = saved
        return TransitionResult(public=public, outcome=outcome)
