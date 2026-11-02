from collections.abc import Sequence

from experiment_extension.mechanism import AllocationMechanism
from simulation_core.game_view import MechanismGameView
from simulation_core.types import SimulationConfig, WorldState


class AllocationGameView(MechanismGameView):
    def __init__(
        self, config: SimulationConfig, state: WorldState, mechanism: AllocationMechanism
    ) -> None:
        super().__init__(config, state, mechanism)

    def budget(self) -> float:
        return float(self.config.world.parameters.get("budget", 10.0))  # type: ignore[arg-type]

    def target(self) -> tuple[float, ...]:
        raw = self.config.world.parameters.get("target", [])
        return tuple(float(x) for x in raw)  # type: ignore[union-attr]
