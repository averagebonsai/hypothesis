from experiment_extension.mechanism import AllocationMechanism

from simulation_core.game_view import MechanismGameView
from simulation_core.types import SimulationConfig, WorldState


class AllocationGameView(MechanismGameView):
    def __init__(
        self, config: SimulationConfig, state: WorldState, mechanism: AllocationMechanism
    ) -> None:
        super().__init__(config, state, mechanism)

    def budget(self) -> float:
        raw = self.config.world.parameters.get("budget", 10.0)
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            raise ValueError("budget must be numeric")
        return float(raw)

    def target(self) -> tuple[float, ...]:
        raw = self.config.world.parameters.get("target", [])
        if not isinstance(raw, (list, tuple)):
            raise ValueError("target must be a vector")
        return tuple(float(x) for x in raw)
