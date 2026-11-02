"""Read-only checks for core-model fixtures; no generated imports or execution."""

import ast
import types
from typing import Union, get_args, get_origin

from pydantic import BaseModel

from simulation_core import execution, problems
from simulation_core import types as core_types


def fixture_issues(source: str, path: str) -> list[str]:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return []  # The ordinary syntax checker reports this separately.
    approved = {module.__name__: module for module in (execution, problems, core_types)}
    models = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in approved:
            for name in node.names:
                model = getattr(approved[node.module], name.name, None)
                if isinstance(model, type) and issubclass(model, BaseModel):
                    models[name.asname or name.name] = model
    issues = []

    def check(annotation: object, value: ast.expr, location: str) -> None:
        origin = get_origin(annotation)
        arguments = get_args(annotation)
        if origin is tuple and isinstance(value, ast.List):
            issues.append(
                f"{path}:{location}: strict tuple field constructed from a Python list; use fixture_config/from_json_values/model_validate_json"
            )
        elif (
            isinstance(annotation, type)
            and issubclass(annotation, BaseModel)
            and isinstance(value, ast.Dict)
        ):
            for key, child in zip(value.keys, value.values):
                if isinstance(key, ast.Constant) and key.value in annotation.model_fields:
                    check(
                        annotation.model_fields[key.value].annotation,
                        child,
                        location + "." + str(key.value),
                    )
        elif origin in (Union, types.UnionType):
            for branch in arguments:
                if isinstance(branch, type) and issubclass(branch, BaseModel):
                    check(branch, value, location)

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "model_validate"
            and isinstance(node.func.value, ast.Name)
            and node.args
        ):
            model = models.get(node.func.value.id)
            if model is not None:
                check(model, node.args[0], node.func.value.id)
    return issues
