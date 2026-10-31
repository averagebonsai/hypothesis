"""Finite normal-form games with arbitrary actor IDs and asymmetric finite choices."""

from collections.abc import Sequence
from math import prod

from pydantic import Field

from simulation_core.mechanism import Mechanism
from simulation_core.types import (
    Action,
    FrozenModel,
    Outcome,
    TransitionResult,
    WorldConfig,
    WorldState,
)


class MovePayload(FrozenModel):
    move: str = Field(min_length=1)


class PayoffCell(FrozenModel):
    moves: dict[str, str]
    payoffs: dict[str, float]


class MatrixParameters(FrozenModel):
    choices: dict[str, list[str]]
    cells: list[PayoffCell]
    action_kind: str
    history_field: str
    payoffs_field: str


class PayoffMatrixMechanism(Mechanism):
    def validate_config(self, config: WorldConfig) -> None:
        params = MatrixParameters.model_validate(config.parameters)
        ids = tuple(actor.id for actor in config.actors)
        if set(params.choices) != set(ids):
            raise ValueError("Choices must cover exactly the configured actors")
        if params.history_field == params.payoffs_field:
            raise ValueError("Output fields must be distinct")
        for actor in config.actors:
            choices = params.choices[actor.id]
            if not choices or len(set(choices)) != len(choices) or any(not c for c in choices):
                raise ValueError("Choices must be nonempty and unique")
            if params.action_kind not in actor.action_space.schemas:
                raise ValueError("Actor must declare the configured action kind")
        profiles = set()
        for cell in params.cells:
            if set(cell.moves) != set(ids) or set(cell.payoffs) != set(ids):
                raise ValueError("Cell must cover every actor")
            if any(cell.moves[aid] not in params.choices[aid] for aid in ids):
                raise ValueError("Payoff table must cover all and only legal profiles")
            profile = tuple(cell.moves[aid] for aid in ids)
            if profile in profiles:
                raise ValueError("Duplicate payoff cell")
            profiles.add(profile)
        if len(profiles) != prod(len(params.choices[aid]) for aid in ids):
            raise ValueError("Payoff table must cover all and only legal profiles")

    def validate_state(self, config: WorldConfig, state: WorldState) -> None:
        params = MatrixParameters.model_validate(config.parameters)
        history = state.public.get(params.history_field, [])
        if not isinstance(history, list) or len(history) != state.tick:
            raise ValueError("History must contain exactly one profile per committed tick")
        for profile in history:
            if not isinstance(profile, dict) or set(profile) != set(params.choices):
                raise ValueError("Invalid history profile")
            if any(profile[aid] not in choices for aid, choices in params.choices.items()):
                raise ValueError("Illegal move in history")
        if state.tick:
            expected = next(cell.payoffs for cell in params.cells if cell.moves == history[-1])
            if state.public.get(params.payoffs_field) != expected:
                raise ValueError("State payoffs disagree with committed profile")

    def validate_actions(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> None:
        self.evaluate(config, state, actions)

    def evaluate(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> Outcome:
        params = MatrixParameters.model_validate(config.parameters)
        if len(actions) != len(config.actors) or {a.actor_id for a in actions} != set(
            params.choices
        ):
            raise ValueError("Expected a complete action profile")
        moves = {}
        for action in actions:
            if action.kind != params.action_kind:
                raise ValueError("Unknown action kind")
            move = MovePayload.model_validate(action.payload).move
            if move not in params.choices[action.actor_id]:
                raise ValueError("Illegal actor choice")
            moves[action.actor_id] = move
        cell = next(cell for cell in params.cells if cell.moves == moves)
        return Outcome(payoffs=cell.payoffs)

    def transition(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> TransitionResult:
        params = MatrixParameters.model_validate(config.parameters)
        outcome = self.evaluate(config, state, actions)
        public = dict(state.public)
        previous = public.get(params.history_field, [])
        if not isinstance(previous, list):
            raise TypeError("Expected a list in the configured records field")
        public[params.history_field] = [
            *previous,
            {a.actor_id: a.payload["move"] for a in actions},
        ]
        public[params.payoffs_field] = dict(outcome.payoffs)
        return TransitionResult(public=public, outcome=outcome)
