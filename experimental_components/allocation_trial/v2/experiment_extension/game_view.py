from collections.abc import Sequence

from simulation_core.mechanism import Mechanism
from simulation_core.solver import GameView
from simulation_core.types import Action, Outcome, SimulationConfig, WorldState


class AllocationGameView(GameView):
    """Isolated evaluator over allocation profiles for the benchmark."""

    def __init__(self, config: SimulationConfig, state: WorldState, mechanism: Mechanism) -> None:
        self.config = config.model_copy(deep=True)
        self.state = state.model_copy(deep=True)
        self.mechanism = mechanism
        mechanism.validate_config(self.config.world.model_copy(deep=True))

    def actor_ids(self) -> tuple[str, ...]:
        return tuple(a.id for a in self.config.world.actors)

    def evaluate(self, profile: Sequence[Action]) -> Outcome:
        return self.mechanism.evaluate(
            self.config.world.model_copy(deep=True),
            self.state.model_copy(deep=True),
            tuple(a.model_copy(deep=True) for a in profile),
        )
