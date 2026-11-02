from collections.abc import Sequence

from experiment_extension.mechanism import AllocationMechanism
from experiment_extension.solver import project_simplex
from simulation_core.solver import BestResponseGameView, BestResponseResult
from simulation_core.types import Action, Outcome, SimulationConfig, WorldState


class AllocationGameView(BestResponseGameView):
    def __init__(
        self, config: SimulationConfig, state: WorldState, mechanism: AllocationMechanism
    ) -> None:
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

    def best_response(self, actor_id: str, profile: Sequence[Action]) -> BestResponseResult:
        if actor_id not in self.actor_ids():
            raise ValueError("Unknown actor")
        current_payoff = self.evaluate(profile).payoffs[actor_id]
        alloc = project_simplex(list(self.target()), self.budget())
        witness = Action.model_validate(
            {"actor_id": actor_id, "kind": "allocate", "payload": {"allocation": alloc}}
        )
        best_payoff = self.evaluate([witness]).payoffs[actor_id]
        gain = max(0.0, float(best_payoff) - float(current_payoff))
        return BestResponseResult(
            actor_id=actor_id,
            current_payoff=float(current_payoff),
            supremum_payoff=float(best_payoff),
            estimated_best_payoff=float(best_payoff),
            gain=float(gain),
            attained=True,
            maximizing_action=witness,
            witness_action=witness,
            witness_payoff=float(best_payoff),
            certification="analytic",
            diagnostics={"method": "simplex projection"},
        )
