from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from typing import ClassVar

from pydantic import BaseModel

from .protocol import DecisionPhase
from .types import Action, Outcome, TransitionResult, WorldConfig, WorldState


class Mechanism(ABC):
    requires_joint_actions: ClassVar[bool] = False

    def required_action_schemas(self, config: WorldConfig) -> dict[str, dict[str, type[BaseModel]]]:
        """Supported action schemas by actor; omitted actors accept registry-validated payloads."""
        return {}

    def validate_schedule(
        self, config: WorldConfig, stages: Iterable[DecisionPhase] | None
    ) -> None:
        if self.requires_joint_actions and stages is not None:
            actors = {actor.id for actor in config.actors}
            if any(
                set(stage.actor_ids) != actors or len(stage.actor_ids) != len(actors)
                for stage in stages
            ):
                raise ValueError(
                    "Mechanism requires one joint action batch from all actors at every stage"
                )

    @abstractmethod
    def validate_config(self, config: WorldConfig) -> None: ...

    @abstractmethod
    def validate_state(self, config: WorldConfig, state: WorldState) -> None: ...

    @abstractmethod
    def validate_actions(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> None: ...

    @abstractmethod
    def evaluate(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> Outcome: ...

    @abstractmethod
    def transition(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> TransitionResult: ...
