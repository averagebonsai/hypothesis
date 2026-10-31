"""User intent is incomplete; execution configuration must be resolved separately."""

from typing import Literal

from pydantic import Field, JsonValue, field_validator

from .provenance import pointer_tokens
from .types import FrozenModel


class SuppliedInput(FrozenModel):
    name: str = Field(min_length=1)
    value: JsonValue
    # Optional until the creating agent maps a user input into execution fields.
    target_path: str | None = None
    source_reference: str | None = None

    @field_validator("target_path")
    @classmethod
    def valid_target(cls, value: str | None) -> str | None:
        if value is not None:
            pointer_tokens(value)
        return value


class ExperimentRequest(FrozenModel):
    schema_version: Literal["experiment.request.v1"] = "experiment.request.v1"
    hypothesis: str = Field(min_length=1)
    supplied_inputs: tuple[SuppliedInput, ...] = ()
    requirements: tuple[str, ...] = ()
    # No automatic assumption generation or component selection occurs in this DTO.
