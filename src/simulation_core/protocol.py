from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from typing import Self

from pydantic import Field, model_validator

from .types import Action, FrozenModel, WorldConfig, WorldState


class DecisionPhase(FrozenModel):
    name: str = Field(min_length=1)
    actor_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_actors(self) -> Self:
        if len(set(self.actor_ids)) != len(self.actor_ids):
            raise ValueError("A phase cannot repeat an actor")
        return self


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

    def validate_config(self, config: WorldConfig) -> None:
        """Optional scheduling preflight; invoked before any actor is called."""

    def declared_phases(self) -> frozenset[str]:
        """Required when a configuration supplies phase-specific permissions."""
        return frozenset()

    def decision_schedule(self, config: WorldConfig) -> Iterable[DecisionPhase] | None:
        """Static schedule when known; None for state-dependent activation."""
        return None
