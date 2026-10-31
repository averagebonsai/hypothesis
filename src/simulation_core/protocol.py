from abc import ABC, abstractmethod
from collections.abc import Sequence

from .types import Action, WorldConfig, WorldState


class ProtocolRules(ABC):
    """Scheduling only. Trusted runtime constructs observations from config permissions."""

    @abstractmethod
    def initial_phase(self) -> str: ...

    @abstractmethod
    def active_actor_ids(self, config: WorldConfig, state: WorldState) -> tuple[str, ...]: ...

    @abstractmethod
    def is_terminal(self, config: WorldConfig, state: WorldState) -> bool: ...

    @abstractmethod
    def validate_action_batch(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> None: ...

    @abstractmethod
    def next_phase(self, config: WorldConfig, state: WorldState) -> str: ...
