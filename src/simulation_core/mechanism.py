from abc import ABC, abstractmethod
from collections.abc import Sequence

from .types import Action, Outcome, TransitionResult, WorldConfig, WorldState


class Mechanism(ABC):
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
