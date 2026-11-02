"""Direct computational jobs do not require actors, policies or simulation state."""

from typing import Literal, Self

from pydantic import Field, JsonValue, model_validator

from simulation_core.provenance import resolve_pointer, same_json
from simulation_core.request import ExperimentRequest
from simulation_core.types import FrozenModel


class ToolInvocation(FrozenModel):
    entrypoint: str = Field(
        pattern=r"^experiment_extension(?:\.[A-Za-z_][A-Za-z0-9_]*)+:[A-Za-z_][A-Za-z0-9_]*$"
    )
    arguments: dict[str, JsonValue] = Field(default_factory=dict)


class ToolJobManifest(FrozenModel):
    schema_version: Literal["tool.job.v1"] = "tool.job.v1"
    request: ExperimentRequest
    tool: ToolInvocation

    @model_validator(mode="after")
    def preserve_supplied_inputs(self) -> Self:
        for item in self.request.supplied_inputs:
            if item.target_path is not None and not same_json(
                resolve_pointer(self.tool.model_dump(mode="json"), item.target_path), item.value
            ):
                raise ValueError(f"Tool invocation overrides supplied input: {item.name}")
        return self


class ToolResult(FrozenModel):
    manifest: ToolJobManifest
    output: JsonValue
