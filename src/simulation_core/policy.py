from abc import ABC, abstractmethod

from pydantic import BaseModel

from .types import Decision, ModelCallRecord, Observation


class Policy(ABC):
    @abstractmethod
    def required_observation_fields(self) -> frozenset[str]: ...

    @abstractmethod
    def choose_action(self, observation: Observation) -> Decision: ...

    def model_calls(self) -> tuple[ModelCallRecord, ...]:
        return ()

    def set_decision_context(self, decision_id: str) -> None:
        """Optional transport identity, separate from the actor-visible observation."""

    def restore_model_calls(self, records: tuple[ModelCallRecord, ...]) -> None:
        """Restore usage for resumable policies; never silently reset a call budget."""
        if records:
            raise ValueError("Policy does not support restoring model calls")

    def configure_action_schemas(self, schemas: dict[str, type[BaseModel]]) -> None:
        """Runtime supplies only this actor's declared payload schemas."""
