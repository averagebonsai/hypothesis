from collections.abc import Sequence

from simulation_core.mechanism import Mechanism
from simulation_core.types import Action, Outcome, TransitionResult, WorldConfig, WorldState


def _params(config: WorldConfig) -> tuple[float, tuple[float, ...]]:
    budget = config.parameters.get("budget")
    target = config.parameters.get("target")
    return float(budget), tuple(float(x) for x in target)  # type: ignore[arg-type]


def _allocation(action: Action) -> tuple[float, ...]:
    raw = action.payload.get("allocation")
    if not isinstance(raw, (list, tuple)):
        raise ValueError("allocation payload must be a vector")
    return tuple(float(x) for x in raw)


class AllocationMechanism(Mechanism):
    """Fixed-sum allocation scored by negative squared distance to target."""

    requires_joint_actions: bool = False  # type: ignore[assignment]

    def validate_config(self, config: WorldConfig) -> None:
        budget, target = _params(config)
        if not (budget > 0):
            raise ValueError("budget must be positive")
        if len(target) < 2:
            raise ValueError("target dimension must be >= 2")
        for x in target:
            if not (x == x) or x in (float("inf"), float("-inf")):
                raise ValueError("target must be finite")

    def validate_state(self, config: WorldConfig, state: WorldState) -> None:
        self.validate_config(config)

    def validate_actions(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> None:
        budget, target = _params(config)
        if len(actions) != 1:
            raise ValueError("Exactly one allocator action required")
        alloc = _allocation(actions[0])
        if len(alloc) != len(target):
            raise ValueError("allocation dimension must match target")
        if any(x < 0 for x in alloc):
            raise ValueError("allocation must be nonnegative")
        if abs(sum(alloc) - budget) > 1e-8:
            raise ValueError("allocation must sum to budget")

    def evaluate(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> Outcome:
        _budget, target = _params(config)
        alloc = _allocation(actions[0])
        score = -sum((a - t) ** 2 for a, t in zip(alloc, target))
        aid = actions[0].actor_id
        return Outcome(payoffs={aid: float(score)}, metrics={"score": float(score)})

    def transition(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> TransitionResult:
        self.validate_actions(config, state, actions)
        outcome = self.evaluate(config, state, actions)
        public = dict(state.public)
        hist = list(public.get("history", []))
        hist.append([a.model_dump(mode="json") for a in actions])
        public["history"] = hist
        public["budget"] = _params(config)[0]
        public["target"] = list(_params(config)[1])
        return TransitionResult(public=public, outcome=outcome)
