from collections.abc import Sequence
from math import isfinite
from typing import ClassVar

from simulation_core.mechanism import Mechanism
from simulation_core.types import Action, Outcome, TransitionResult, WorldConfig, WorldState


def _params(config: WorldConfig) -> tuple[float, tuple[float, ...]]:
    budget_raw = config.parameters.get("budget")
    target_raw = config.parameters.get("target")
    if isinstance(budget_raw, bool) or not isinstance(budget_raw, (int, float)):
        raise TypeError("budget must be a number")
    if not isinstance(target_raw, (list, tuple)):
        raise TypeError("target must be a vector")
    budget = float(budget_raw)
    items: list[float] = []
    for x in target_raw:
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            raise TypeError("target entries must be numbers")
        items.append(float(x))
    return budget, tuple(items)


def _allocation(action: Action) -> tuple[float, ...]:
    raw = action.payload.get("allocation")
    if not isinstance(raw, (list, tuple)):
        raise TypeError("allocation payload must be a vector")
    out: list[float] = []
    for x in raw:
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            raise TypeError("allocation entries must be numbers")
        out.append(float(x))
    return tuple(out)


class AllocationMechanism(Mechanism):
    """Fixed-sum allocation scored by negative squared distance to target."""

    requires_joint_actions: ClassVar[bool] = False

    def validate_config(self, config: WorldConfig) -> None:
        budget, target = _params(config)
        if not (isfinite(budget) and budget > 0):
            raise ValueError("budget must be positive")
        if len(target) < 2:
            raise ValueError("target dimension must be >= 2")
        for x in target:
            if not isfinite(x):
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
        hist_raw = public.get("history", [])
        if not isinstance(hist_raw, list):
            raise TypeError("history must be a list")
        hist = list(hist_raw)
        hist.append([a.model_dump(mode="json") for a in actions])
        public["history"] = hist
        budget, target = _params(config)
        public["budget"] = budget
        public["target"] = list(target)
        return TransitionResult(public=public, outcome=outcome)
