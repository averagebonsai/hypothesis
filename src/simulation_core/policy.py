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

    def configure_action_schemas(self, schemas: dict[str, type[BaseModel]]) -> None:
        """Runtime supplies only this actor's declared payload schemas."""
