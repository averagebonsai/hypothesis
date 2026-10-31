from collections.abc import Sequence

from pydantic import Field, JsonValue

from simulation_core.protocol import ProtocolRules
from simulation_core.types import Action, FrozenModel, WorldConfig, WorldState


class RoundParameters(FrozenModel):
    rounds: int = Field(gt=0)
    active_phase: str = "act"
    terminal_phase: str = "finished"


class SimultaneousProtocol(ProtocolRules):
    def __init__(self, parameters: dict[str, JsonValue]):
        self.parameters = RoundParameters.model_validate(parameters)

    def initial_phase(self) -> str:
        return self.parameters.active_phase

    def active_actor_ids(self, config: WorldConfig, state: WorldState) -> tuple[str, ...]:
        return tuple(actor.id for actor in config.actors)

    def is_terminal(self, config: WorldConfig, state: WorldState) -> bool:
        return state.tick >= self.parameters.rounds

    def validate_action_batch(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> None:
        ids = [action.actor_id for action in actions]
        if len(ids) != len(set(ids)) or set(ids) != set(self.active_actor_ids(config, state)):
            raise ValueError("Exactly one action required per active actor")

    def next_phase(self, config: WorldConfig, state: WorldState) -> str:
        return (
            self.parameters.terminal_phase
            if state.tick + 1 >= self.parameters.rounds
            else self.parameters.active_phase
        )
