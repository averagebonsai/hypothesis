"""Direct callable execution inside the same restricted worker, without a runtime loop."""

import importlib
import inspect
import json

from pydantic import BaseModel, JsonValue, TypeAdapter

from agent_tools.jobs import ToolJobManifest, ToolResult
from agent_tools.specs import BundleManifest


def execute_tool(job: ToolJobManifest, bundle: BundleManifest | None = None) -> ToolResult:
    from .runtime import require_container

    require_container()
    module, name = job.tool.entrypoint.split(":")
    function = getattr(importlib.import_module(module), name)
    if not callable(function):
        raise TypeError("Tool entrypoint must be callable")
    arguments = dict(job.tool.arguments)
    contract = (
        next(
            (
                component
                for component in bundle.components
                if component.symbol == job.tool.entrypoint
            ),
            None,
        )
        if bundle is not None
        else None
    )
    if contract is not None and contract.input_model is not None:
        input_module, input_name = contract.input_model.split(":")
        input_model = getattr(importlib.import_module(input_module), input_name)
        if not isinstance(input_model, type) or not issubclass(input_model, BaseModel):
            raise TypeError("Tool input model must be a Pydantic class")
        arguments = input_model.model_validate_json(
            json.dumps(arguments, allow_nan=False)
        ).model_dump()
    inspect.signature(function).bind(**arguments)
    output = function(**arguments)
    if isinstance(output, BaseModel):
        output = output.model_dump(mode="json")
    if contract is not None and contract.output_model is not None:
        output_module, output_name = contract.output_model.split(":")
        output_model = getattr(importlib.import_module(output_module), output_name)
        if not isinstance(output_model, type) or not issubclass(output_model, BaseModel):
            raise TypeError("Tool output model must be a Pydantic class")
        output = output_model.model_validate_json(json.dumps(output, allow_nan=False)).model_dump(
            mode="json"
        )
    # Only JSON-compatible values cross the host boundary; no pickle or imports.
    value = TypeAdapter(JsonValue).validate_json(json.dumps(output, allow_nan=False))
    return ToolResult(manifest=job, output=value)
