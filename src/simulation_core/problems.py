"""Declarative numeric problems. Expressions are data, never executable Python."""

from collections.abc import Mapping
from math import isfinite
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .types import FrozenModel

type Numeric = float | tuple[float, ...]


class Constant(FrozenModel):
    kind: Literal["constant"] = "constant"
    value: Numeric

    @model_validator(mode="after")
    def nonempty_vector(self) -> Self:
        if isinstance(self.value, tuple) and not self.value:
            raise ValueError("Constant vectors must be nonempty")
        return self


class Reference(FrozenModel):
    kind: Literal["reference"] = "reference"
    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*$")


class Operation(FrozenModel):
    kind: Literal["operation"] = "operation"
    operator: Literal["add", "subtract", "multiply", "dot", "sum", "square", "negate"]
    arguments: tuple["Expression", ...] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def arity(self) -> Self:
        expected = 1 if self.operator in {"sum", "square", "negate"} else 2
        if len(self.arguments) != expected:
            raise ValueError("Incorrect expression arity")
        return self


type Expression = Annotated[Constant | Reference | Operation, Field(discriminator="kind")]
Operation.model_rebuild()


class ProblemActor(FrozenModel):
    id: str = Field(min_length=1)
    description: str = ""


class VariableSpec(FrozenModel):
    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    actor_id: str | None = None
    shape: Literal["scalar", "vector"]
    # A string refers to a vector parameter whose length determines the dimension.
    dimension: int | str = 1
    domain: Literal["continuous", "integer"] = "continuous"
    lower: Numeric | None = None
    upper: Numeric | None = None


class ObjectiveSpec(FrozenModel):
    name: str = Field(min_length=1)
    actor_id: str | None = None
    sense: Literal["maximize", "minimize"]
    expression: Expression


class ConstraintSpec(FrozenModel):
    name: str = Field(min_length=1)
    left: Expression
    relation: Literal["eq", "le", "ge"]
    right: Expression


def _shape(value: Numeric) -> int:
    return len(value) if isinstance(value, tuple) else 0


def expression_shape(expression: Expression, shapes: Mapping[str, int]) -> int:
    if isinstance(expression, Constant):
        return _shape(expression.value)
    if isinstance(expression, Reference):
        if expression.name not in shapes:
            raise ValueError(f"Unknown expression reference: {expression.name}")
        return shapes[expression.name]
    dimensions = [expression_shape(arg, shapes) for arg in expression.arguments]
    first = dimensions[0]
    if expression.operator == "sum":
        if first == 0:
            raise ValueError("sum requires a vector")
        return 0
    if expression.operator in {"square", "negate"}:
        return first
    second = dimensions[1]
    if expression.operator == "multiply":
        if first and second:
            raise ValueError("Use dot for two vectors")
        return max(first, second)
    if first != second or (expression.operator == "dot" and first == 0):
        raise ValueError("Expression dimensions do not match")
    return 0 if expression.operator == "dot" else first


def evaluate_expression(expression: Expression, values: Mapping[str, Numeric]) -> Numeric:
    if isinstance(expression, Constant):
        result = expression.value
    elif isinstance(expression, Reference):
        result = values[expression.name]
    else:
        args = [evaluate_expression(arg, values) for arg in expression.arguments]
        first = args[0]
        if expression.operator == "sum":
            if not isinstance(first, tuple):
                raise ValueError("sum requires a vector")
            result = sum(first)
        elif expression.operator in {"square", "negate"}:

            def unary(value: float) -> float:
                return value * value if expression.operator == "square" else -value

            result = tuple(unary(x) for x in first) if isinstance(first, tuple) else unary(first)
        else:
            second = args[1]
            if expression.operator == "dot":
                if (
                    not isinstance(first, tuple)
                    or not isinstance(second, tuple)
                    or len(first) != len(second)
                ):
                    raise ValueError("dot requires equally sized vectors")
                result = sum(x * y for x, y in zip(first, second))
            elif expression.operator == "multiply":
                if isinstance(first, tuple) and not isinstance(second, tuple):
                    result = tuple(x * second for x in first)
                elif isinstance(second, tuple) and not isinstance(first, tuple):
                    result = tuple(first * x for x in second)
                elif not isinstance(first, tuple) and not isinstance(second, tuple):
                    result = first * second
                else:
                    raise ValueError("Vector multiplication is not implicit")
            else:

                def binary(x: float, y: float) -> float:
                    return x + y if expression.operator == "add" else x - y

                if (
                    isinstance(first, tuple)
                    and isinstance(second, tuple)
                    and len(first) == len(second)
                ):
                    result = tuple(binary(x, y) for x, y in zip(first, second))
                elif not isinstance(first, tuple) and not isinstance(second, tuple):
                    result = binary(first, second)
                else:
                    raise ValueError("Expression dimensions do not match")
    if not all(isfinite(value) for value in (result if isinstance(result, tuple) else (result,))):
        raise ArithmeticError("Nonfinite expression result")
    return result


class ProblemEvaluation(FrozenModel):
    feasible: bool
    objectives: dict[str, float]
    constraint_residuals: dict[str, float]
    violations: tuple[str, ...]


class ProblemStatement(FrozenModel):
    schema_version: Literal["problem.statement.v1"] = "problem.statement.v1"
    description: str = Field(min_length=1)
    actors: tuple[ProblemActor, ...] = ()
    parameters: dict[str, Numeric] = Field(default_factory=dict)
    variables: tuple[VariableSpec, ...] = Field(min_length=1, max_length=64)
    objectives: tuple[ObjectiveSpec, ...] = Field(default=(), max_length=64)
    constraints: tuple[ConstraintSpec, ...] = Field(default=(), max_length=256)
    timing: str = "unspecified"
    evaluation: Literal["deterministic", "stochastic", "unknown"] = "unknown"
    requirements: tuple[str, ...] = ()
    feasibility_tolerance: float = Field(default=1e-8, ge=0)

    def dimension(self, variable: VariableSpec) -> int:
        if isinstance(variable.dimension, str):
            parameter = self.parameters.get(variable.dimension)
            size = _shape(parameter) if parameter is not None else 0
            if size == 0:
                raise ValueError("Dimension reference must name a nonempty vector parameter")
            return size
        return variable.dimension

    @model_validator(mode="after")
    def references_and_dimensions(self) -> Self:
        actor_ids = [actor.id for actor in self.actors]
        variable_ids = [variable.name for variable in self.variables]
        if len(set(actor_ids)) != len(actor_ids) or len(set(variable_ids)) != len(variable_ids):
            raise ValueError("Duplicate actors or variables")
        if set(variable_ids) & self.parameters.keys():
            raise ValueError("Variable and parameter namespaces must be disjoint")
        shapes = {name: _shape(value) for name, value in self.parameters.items()}
        if any(isinstance(value, tuple) and not value for value in self.parameters.values()):
            raise ValueError("Vector parameters must be nonempty")
        for variable in self.variables:
            size = self.dimension(variable)
            if size < 1 or size > 256 or (variable.shape == "scalar" and size != 1):
                raise ValueError("Invalid variable dimension")
            if variable.actor_id is not None and variable.actor_id not in actor_ids:
                raise ValueError("Unknown variable owner")
            shape = size if variable.shape == "vector" else 0
            shapes[variable.name] = shape
            for bound in (variable.lower, variable.upper):
                if isinstance(bound, tuple) and (not shape or len(bound) != size):
                    raise ValueError("Bound dimensions do not match variable")
            if variable.lower is not None and variable.upper is not None:
                lows = (
                    variable.lower
                    if isinstance(variable.lower, tuple)
                    else (variable.lower,) * size
                )
                highs = (
                    variable.upper
                    if isinstance(variable.upper, tuple)
                    else (variable.upper,) * size
                )
                if any(low > high for low, high in zip(lows, highs)):
                    raise ValueError("Variable bounds are reversed")
        for objective in self.objectives:
            if objective.actor_id is not None and objective.actor_id not in actor_ids:
                raise ValueError("Unknown objective owner")
            if expression_shape(objective.expression, shapes) != 0:
                raise ValueError("Objective must be scalar")
        for constraint in self.constraints:
            if (
                expression_shape(constraint.left, shapes) != 0
                or expression_shape(constraint.right, shapes) != 0
            ):
                raise ValueError(
                    "Constraint sides must be scalar; vector bounds belong in variables"
                )
        if len({obj.name for obj in self.objectives}) != len(self.objectives) or len(
            {c.name for c in self.constraints}
        ) != len(self.constraints):
            raise ValueError("Duplicate objective or constraint names")
        return self

    def evaluate(self, assignments: dict[str, Numeric]) -> ProblemEvaluation:
        if set(assignments) != {variable.name for variable in self.variables}:
            raise ValueError("Assignments must cover exactly the variables")
        violations = []
        for variable in self.variables:
            value = assignments[variable.name]
            expected_shape = self.dimension(variable) if variable.shape == "vector" else 0
            if _shape(value) != expected_shape:
                raise ValueError("Assignment shape mismatch")
            coordinates = value if isinstance(value, tuple) else (value,)
            if not all(isfinite(x) for x in coordinates):
                raise ValueError("Assignments must be finite")
            if variable.domain == "integer" and any(not float(x).is_integer() for x in coordinates):
                violations.append(variable.name + ":integer")
            for bound, kind in ((variable.lower, "lower"), (variable.upper, "upper")):
                if bound is None:
                    continue
                values = bound if isinstance(bound, tuple) else (bound,) * len(coordinates)
                if any(
                    (
                        x < limit - self.feasibility_tolerance
                        if kind == "lower"
                        else x > limit + self.feasibility_tolerance
                    )
                    for x, limit in zip(coordinates, values)
                ):
                    violations.append(variable.name + ":" + kind)
        context = {**self.parameters, **assignments}
        objectives = {}
        for objective in self.objectives:
            value = evaluate_expression(objective.expression, context)
            if isinstance(value, tuple):
                raise TypeError("Objective is not scalar")
            objectives[objective.name] = value
        residuals = {}
        for constraint in self.constraints:
            left = evaluate_expression(constraint.left, context)
            right = evaluate_expression(constraint.right, context)
            if isinstance(left, tuple) or isinstance(right, tuple):
                raise TypeError("Constraint is not scalar")
            residual = left - right
            residuals[constraint.name] = residual
            tolerance = self.feasibility_tolerance
            if (
                (constraint.relation == "eq" and abs(residual) > tolerance)
                or (constraint.relation == "le" and residual > tolerance)
                or (constraint.relation == "ge" and residual < -tolerance)
            ):
                violations.append(constraint.name)
        return ProblemEvaluation(
            feasible=not violations,
            objectives=objectives,
            constraint_residuals=residuals,
            violations=tuple(violations),
        )
