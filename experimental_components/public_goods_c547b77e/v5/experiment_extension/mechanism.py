"""Saved-balance public-goods mechanism with a known endowment withdrawal.

Each round every participant contributes any finite nonnegative amount up to
their available funds (saved balance plus that round's endowment). After the
joint batch commits, the pool pays out ``multiplier * total / N`` to each
participant and savings update to opening balance plus round payoff. Completed
rounds publish contributions, payoffs and balances to all participants; the
mechanism never touches private memory, so policies keep writable memory under
the runtime single-writer rule.
"""

from collections.abc import Sequence
from math import isfinite
from typing import Self

from experiment_extension.schemas import ContributionPayload
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

ACTION_KIND = "contribute"

ROUND_KEY = "round"
ROUNDS_KEY = "rounds"
ENDOWED_ROUNDS_KEY = "endowed_rounds"
ENDOWMENT_KEY = "endowment"
MULTIPLIER_KEY = "multiplier"
ROUND_ENDOWMENT_KEY = "endowment_this_round"
BALANCES_KEY = "balances"
HISTORY_KEY = "history"


class PublicGoodsParameters(FrozenModel):
    participant_count: int = Field(ge=2)
    rounds: int = Field(ge=1)
    endowed_rounds: int = Field(ge=0)
    endowment: float = Field(ge=0)
    multiplier: float = Field(ge=0)

    @model_validator(mode="after")
    def _schedule_within_horizon(self) -> Self:
        if self.endowed_rounds > self.rounds:
            raise ValueError("endowed_rounds cannot exceed rounds")
        return self


def scheduled_endowment(params: PublicGoodsParameters, round_no: int) -> float:
    """Return the per-participant endowment for a 1-indexed round number."""
    return params.endowment if round_no <= params.endowed_rounds else 0.0


def round_economics(
    ordered: Sequence[tuple[str, float]], endowment: float, multiplier: float
) -> tuple[float, float, dict[str, float]]:
    """Split a joint batch into total, per-capita payout and round payoffs."""
    total = sum(amount for _, amount in ordered)
    payout = multiplier * total / len(ordered)
    payoffs = {aid: endowment - amount + payout for aid, amount in ordered}
    return total, payout, payoffs


def as_number(value: JsonValue, what: str) -> float:
    """Narrow a JSON value to a finite float, rejecting bools and nonnumerics."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{what} must be numeric")  # noqa: TRY004
    if not isfinite(value):
        raise ValueError(f"{what} must be finite")
    return float(value)


class PublicGoodsMechanism(Mechanism):
    requires_joint_actions = True

    def required_action_schemas(self, config: WorldConfig) -> dict[str, dict[str, type[BaseModel]]]:
        return {actor.id: {ACTION_KIND: ContributionPayload} for actor in config.actors}

    def _params(self, config: WorldConfig) -> PublicGoodsParameters:
        return PublicGoodsParameters.model_validate(config.parameters)

    def validate_config(self, config: WorldConfig) -> None:
        params = self._params(config)
        if len(config.actors) != params.participant_count:
            raise ValueError("participant_count must match the configured actors")
        for actor in config.actors:
            if ACTION_KIND not in actor.action_space.schemas:
                raise ValueError(f"Actor {actor.id} must declare the contribute action")

    def validate_actions(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> None:
        params = self._params(config)
        expected = [actor.id for actor in config.actors]
        ids = [action.actor_id for action in actions]
        if len(ids) != len(expected) or set(ids) != set(expected) or len(set(ids)) != len(ids):
            raise ValueError("Expected one joint contribute action per actor")
        balances = state.public.get(BALANCES_KEY)
        if not isinstance(balances, dict):
            raise ValueError("Public balances are missing")  # noqa: TRY004
        endowment = scheduled_endowment(params, state.tick + 1)
        for action in actions:
            if action.kind != ACTION_KIND:
                raise ValueError("Invalid action kind")
            amount = as_number(action.payload.get("contribution"), "contribution")
            ContributionPayload.model_validate({"contribution": amount})
            if action.actor_id not in balances:
                raise ValueError("Actor balance is missing")
            saved = as_number(balances[action.actor_id], "saved balance")
            if amount > saved + endowment:
                raise ValueError("Contribution exceeds available funds")

    def _ordered_amounts(
        self, config: WorldConfig, actions: Sequence[Action]
    ) -> list[tuple[str, float]]:
        by_actor = {action.actor_id: action for action in actions}
        return [
            (
                actor.id,
                as_number(by_actor[actor.id].payload.get("contribution"), "contribution"),
            )
            for actor in config.actors
        ]

    def evaluate(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> Outcome:
        self.validate_actions(config, state, actions)
        params = self._params(config)
        endowment = scheduled_endowment(params, state.tick + 1)
        ordered = self._ordered_amounts(config, actions)
        total, payout, payoffs = round_economics(ordered, endowment, params.multiplier)
        return Outcome(
            payoffs=payoffs,
            metrics={
                ROUND_KEY: state.tick + 1,
                ROUND_ENDOWMENT_KEY: endowment,
                "total_contribution": total,
                "per_capita_payout": payout,
            },
        )

    def transition(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> TransitionResult:
        outcome = self.evaluate(config, state, actions)
        params = self._params(config)
        endowment = scheduled_endowment(params, state.tick + 1)
        balances = state.public[BALANCES_KEY]
        assert isinstance(balances, dict)
        ordered = self._ordered_amounts(config, actions)
        total, payout, _ = round_economics(ordered, endowment, params.multiplier)
        contributions: dict[str, JsonValue] = {aid: amount for aid, amount in ordered}
        stored_payoffs: dict[str, JsonValue] = {
            aid: value for aid, value in outcome.payoffs.items()
        }
        history = state.public.get(HISTORY_KEY, [])
        if not isinstance(history, list):
            raise TypeError("History must be a list")
        public: dict[str, JsonValue] = dict(state.public)
        public[HISTORY_KEY] = [
            *history,
            {
                ROUND_KEY: state.tick + 1,
                ENDOWMENT_KEY: endowment,
                "contributions": contributions,
                "total_contribution": total,
                "per_capita_payout": payout,
                "payoffs": stored_payoffs,
            },
        ]
        public[BALANCES_KEY] = {
            actor.id: as_number(balances[actor.id], "saved balance")
            + float(outcome.payoffs[actor.id])
            for actor in config.actors
        }
        public[ROUND_KEY] = state.tick + 2
        public[ROUND_ENDOWMENT_KEY] = scheduled_endowment(params, state.tick + 2)
        return TransitionResult(public=public, outcome=outcome)

    def validate_state(self, config: WorldConfig, state: WorldState) -> None:
        params = self._params(config)
        ids = [actor.id for actor in config.actors]
        public = state.public
        if public.get(ROUND_KEY) != state.tick + 1:
            raise ValueError("Public round must equal tick + 1")
        mirrors = {
            ROUNDS_KEY: params.rounds,
            ENDOWED_ROUNDS_KEY: params.endowed_rounds,
            ENDOWMENT_KEY: params.endowment,
            MULTIPLIER_KEY: params.multiplier,
        }
        for key, want in mirrors.items():
            if public.get(key) != want:
                raise ValueError(f"Public mirror of {key} disagrees with parameters")
        if public.get(ROUND_ENDOWMENT_KEY) != scheduled_endowment(params, state.tick + 1):
            raise ValueError("Public endowment disagrees with the withdrawal schedule")
        balances = public.get(BALANCES_KEY)
        if not isinstance(balances, dict) or set(balances) != set(ids):
            raise ValueError("Balances must cover exactly the configured actors")
        for aid in ids:
            if as_number(balances[aid], "saved balance") < 0:
                raise ValueError("Saved balances cannot be negative")
        history = public.get(HISTORY_KEY)
        if not isinstance(history, list) or len(history) != state.tick:
            raise ValueError("History must contain one entry per committed tick")
        running = {aid: 0.0 for aid in ids}
        for index, entry in enumerate(history, start=1):
            if not isinstance(entry, dict):
                raise ValueError("Invalid history entry")  # noqa: TRY004
            if entry.get(ROUND_KEY) != index:
                raise ValueError("History rounds must be sequential")
            if entry.get(ENDOWMENT_KEY) != scheduled_endowment(params, index):
                raise ValueError("History endowment disagrees with the schedule")
            stored = entry.get("contributions")
            if not isinstance(stored, dict) or set(stored) != set(ids):
                raise ValueError("History contributions must cover all actors")
            ordered = [(aid, as_number(stored[aid], "stored contribution")) for aid in ids]
            if any(amount < 0 for _, amount in ordered):
                raise ValueError("Stored contributions cannot be negative")
            endowment = as_number(entry.get(ENDOWMENT_KEY), "stored endowment")
            total, payout, payoffs = round_economics(ordered, endowment, params.multiplier)
            if entry.get("total_contribution") != total:
                raise ValueError("Stored total disagrees with contributions")
            if entry.get("per_capita_payout") != payout:
                raise ValueError("Stored payout disagrees with contributions")
            stored_payoffs = entry.get("payoffs")
            if not isinstance(stored_payoffs, dict):
                raise ValueError("Stored payoffs are missing")  # noqa: TRY004
            for aid in ids:
                if stored_payoffs.get(aid) != payoffs[aid]:
                    raise ValueError("Stored payoff disagrees with contributions")
                running[aid] += payoffs[aid]
        for aid in ids:
            if as_number(balances[aid], "saved balance") != running[aid]:
                raise ValueError("Balances must equal cumulative recorded payoffs")
