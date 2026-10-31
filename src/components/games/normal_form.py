"""Complete-information finite-action view; snapshots and oracle inputs are isolated."""

from collections.abc import Sequence

from components.mechanisms.normal_form import MatrixParameters
from simulation_core.mechanism import Mechanism
from simulation_core.solver import GameView
from simulation_core.types import Action, Outcome, SimulationConfig, WorldState


class NormalFormGameView(GameView):
    def __init__(self, config: SimulationConfig, state: WorldState, mechanism: Mechanism) -> None:
        self.config = config.model_copy(deep=True)
        self.state = state.model_copy(deep=True)
        self.mechanism = mechanism
        mechanism.validate_config(self.config.world.model_copy(deep=True))
        self.parameters = MatrixParameters.model_validate(self.config.world.parameters)

    def actor_ids(self) -> tuple[str, ...]:
        return tuple(actor.id for actor in self.config.world.actors)

    def actions(self, actor_id: str) -> tuple[Action, ...]:
        return tuple(
            Action(actor_id=actor_id, kind=self.parameters.action_kind, payload={"move": move})
            for move in self.parameters.choices[actor_id]
        )

    def evaluate(self, profile: Sequence[Action]) -> Outcome:
        return self.mechanism.evaluate(
            self.config.world.model_copy(deep=True),
            self.state.model_copy(deep=True),
            tuple(action.model_copy(deep=True) for action in profile),
        )
