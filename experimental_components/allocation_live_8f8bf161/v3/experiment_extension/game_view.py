from simulation_core.game_view import MechanismGameView
from simulation_core.types import SimulationConfig, WorldState

from experiment_extension.mechanism import AllocationMechanism


class AllocationGameView(MechanismGameView):
    def __init__(
        self, config: SimulationConfig, state: WorldState, mechanism: AllocationMechanism
    ) -> None:
        super().__init__(config, state, mechanism)

    def budget(self) -> float:
        raw = self.config.world.parameters.get("budget", 10.0)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise TypeError("budget must be numeric")
        return float(raw)

    def target(self) -> tuple[float, ...]:
        raw = self.config.world.parameters.get("target", [])
        if not isinstance(raw, (list, tuple)):
            raise TypeError("target must be a vector")
        items: list[float] = []
        for x in raw:
            if isinstance(x, bool) or not isinstance(x, (int, float)):
                raise TypeError("target entries must be numeric")
            items.append(float(x))
        return tuple(items)
