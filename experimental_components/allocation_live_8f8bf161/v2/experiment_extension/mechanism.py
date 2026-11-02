from collections.abc import Sequence

from experiment_extension.schemas import AllocationPayload
from pydantic import BaseModel
from simulation_core.mechanism import Mechanism
from simulation_core.types import Action, Outcome, TransitionResult, WorldConfig, WorldState


def _params(config: WorldConfig) -> tuple[float, tuple[float, ...]]:
    raw_b = config.parameters.get("budget", config.initial_public_state.get("budget"))
    raw_t = config.parameters.get("target", config.initial_public_state.get("target"))
    if not isinstance(raw_b, (int, float)) or isinstance(raw_b, bool):
        raise ValueError("budget must be numeric")
    if not isinstance(raw_t, (list, tuple)):
        raise ValueError("target must be a vector")
    budget = float(raw_b)
    target = tuple(float(x) for x in raw_t)
    for x in target:
        float(x)
    return budget, target


class AllocationMechanism(Mechanism):
    def required_action_schemas(
        self, config: WorldConfig
    ) -> dict[str, dict[str, type[BaseModel]]]:
        return {actor.id: {"allocate": AllocationPayload} for actor in config.actors}

    def validate_config(self, config: WorldConfig) -> None:
        budget, target = _params(config)
        if not budget > 0:
            raise ValueError("budget must be positive")
        if len(target) < 2:
            raise ValueError("target dimension must be >= 2")
        if len(config.actors) != 1:
            raise ValueError("Expected exactly one actor")

    def validate_state(self, config: WorldConfig, state: WorldState) -> None:
        _params(config)

    def validate_actions(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> None:
        _, target = _params(config)
        if len(actions) != 1:
            raise ValueError("Expected one action")
        action = actions[0]
        if action.kind != "allocate":
            raise ValueError("Unknown action kind")
        payload = AllocationPayload.model_validate(action.payload)
        if len(payload.allocation) != len(target):
            raise ValueError("allocation dimension must match target")

    def evaluate(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> Outcome:
        self.validate_actions(config, state, actions)
        _, target = _params(config)
        payload = AllocationPayload.model_validate(actions[0].payload)
        score = -sum((a - t) ** 2 for a, t in zip(payload.allocation, target))
        return Outcome(
            payoffs={actions[0].actor_id: float(score)},
            metrics={"total": float(sum(payload.allocation))},
        )

    def transition(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> TransitionResult:
        outcome = self.evaluate(config, state, actions)
        payload = AllocationPayload.model_validate(actions[0].payload)
        public = dict(state.public)
        public["allocation"] = list(payload.allocation)
        return TransitionResult(public=public, outcome=outcome)
