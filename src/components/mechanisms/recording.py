"""Generic action collection: no utilities, economic assumptions, or action-specific fields."""

from collections.abc import Sequence

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


class NumericPayload(FrozenModel):
    value: float


class RecordingParameters(FrozenModel):
    records_field: str = Field(min_length=1)
    count_metric: str = Field(min_length=1)


class RecordingMechanism(Mechanism):
    def validate_config(self, config: WorldConfig) -> None:
        RecordingParameters.model_validate(config.parameters)

    def validate_state(self, config: WorldConfig, state: WorldState) -> None:
        params = RecordingParameters.model_validate(config.parameters)
        records = state.public.get(params.records_field, [])
        if not isinstance(records, list) or len(records) != state.tick:
            raise ValueError("Records must contain one batch per committed tick")

    def validate_actions(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> None:
        if {a.actor_id for a in actions} - {a.id for a in config.actors}:
            raise ValueError("Unknown actor in action batch")

    def evaluate(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> Outcome:
        params = RecordingParameters.model_validate(config.parameters)
        return Outcome(metrics={params.count_metric: len(actions)})

    def transition(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> TransitionResult:
        params = RecordingParameters.model_validate(config.parameters)
        public = dict(state.public)
        previous = public.get(params.records_field, [])
        if not isinstance(previous, list):
            raise TypeError("Expected a list in the configured records field")
        public[params.records_field] = [
            *previous,
            [action.model_dump(mode="json") for action in actions],
        ]
        return TransitionResult(public=public, outcome=self.evaluate(config, state, actions))
