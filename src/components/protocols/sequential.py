"""Reusable finite phase schedule; observation projection remains trusted core code."""

from collections.abc import Iterable, Sequence
from typing import Self

from pydantic import Field, JsonValue, model_validator

from simulation_core.protocol import DecisionPhase, ProtocolRules
from simulation_core.types import Action, FrozenModel, WorldConfig, WorldState


class SequentialParameters(FrozenModel):
    phases: tuple[DecisionPhase, ...] = Field(min_length=1)
    terminal_phase: str = Field(default="finished", min_length=1)

    @model_validator(mode="after")
    def unique_phases(self) -> Self:
        names = [phase.name for phase in self.phases]
        if len(set(names)) != len(names) or self.terminal_phase in names:
            raise ValueError("Decision and terminal phase names must be distinct")
        return self


class SequentialProtocol(ProtocolRules):
    def __init__(self, parameters: dict[str, JsonValue]) -> None:
        self.parameters = SequentialParameters.from_json_values(parameters)

    def validate_config(self, config: WorldConfig) -> None:
        ids = {actor.id for actor in config.actors}
        if any(set(phase.actor_ids) - ids for phase in self.parameters.phases):
            raise ValueError("Unknown actor in sequential schedule")

    def declared_phases(self) -> frozenset[str]:
        return frozenset(
            [phase.name for phase in self.parameters.phases] + [self.parameters.terminal_phase]
        )

    def initial_phase(self) -> str:
        return self.parameters.phases[0].name

    def _index(self, state: WorldState) -> int:
        if state.tick > len(self.parameters.phases):
            raise ValueError("State tick exceeds the finite phase schedule")
        expected = (
            self.parameters.terminal_phase
            if state.tick >= len(self.parameters.phases)
            else self.parameters.phases[state.tick].name
        )
        if state.phase != expected:
            raise ValueError("State phase disagrees with the configured schedule")
        return state.tick

    def active_actor_ids(self, config: WorldConfig, state: WorldState) -> tuple[str, ...]:
        index = self._index(state)
        return (
            self.parameters.phases[index].actor_ids if index < len(self.parameters.phases) else ()
        )

    def is_terminal(self, config: WorldConfig, state: WorldState) -> bool:
        return self._index(state) >= len(self.parameters.phases)

    def validate_action_batch(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> None:
        ids = [action.actor_id for action in actions]
        if len(set(ids)) != len(ids) or set(ids) != set(self.active_actor_ids(config, state)):
            raise ValueError("Expected exactly one action from each active phase actor")

    def next_phase(self, config: WorldConfig, state: WorldState) -> str:
        index = self._index(state) + 1
        return (
            self.parameters.phases[index].name
            if index < len(self.parameters.phases)
            else self.parameters.terminal_phase
        )

    def decision_schedule(self, config: WorldConfig) -> Iterable[DecisionPhase]:
        return iter(self.parameters.phases)
