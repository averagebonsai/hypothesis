"""Reusable adapter from a mechanism to an isolated mathematical evaluator."""

from collections.abc import Sequence

from .mechanism import Mechanism
from .solver import GameView
from .types import Action, Outcome, SimulationConfig, WorldState


class MechanismGameView(GameView):
    def __init__(self, config: SimulationConfig, state: WorldState, mechanism: Mechanism) -> None:
        self.config = config.model_copy(deep=True)
        self.state = state.model_copy(deep=True)
        self.mechanism = mechanism
        mechanism.validate_config(self.config.world.model_copy(deep=True))

    def actor_ids(self) -> tuple[str, ...]:
        return tuple(actor.id for actor in self.config.world.actors)

    def evaluate(self, profile: Sequence[Action]) -> Outcome:
        return self.mechanism.evaluate(
            self.config.world.model_copy(deep=True),
            self.state.model_copy(deep=True),
            tuple(action.model_copy(deep=True) for action in profile),
        )
