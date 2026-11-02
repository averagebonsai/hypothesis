import pytest
from pydantic import ValidationError

from simulation_core.problems import (
    Constant,
    ConstraintSpec,
    ObjectiveSpec,
    Operation,
    ProblemStatement,
    Reference,
    VariableSpec,
)
from simulation_core.request import ExperimentRequest


def problem():
    return ProblemStatement(
        description="Numeric allocation example",
        parameters={"capacity": 6.0, "desired": (2.0, 2.0)},
        variables=(VariableSpec(name="choices", shape="vector", dimension="desired", lower=0.0),),
        objectives=(
            ObjectiveSpec(
                name="loss",
                sense="minimize",
                expression=Operation(
                    operator="sum",
                    arguments=(
                        Operation(
                            operator="square",
                            arguments=(
                                Operation(
                                    operator="subtract",
                                    arguments=(
                                        Reference(name="choices"),
                                        Reference(name="desired"),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
        constraints=(
            ConstraintSpec(
                name="capacity",
                left=Operation(operator="sum", arguments=(Reference(name="choices"),)),
                relation="eq",
                right=Reference(name="capacity"),
            ),
        ),
    )


def test_structured_request_roundtrip_and_safe_evaluation():
    statement = problem()
    request = ExperimentRequest(hypothesis="User-defined numeric model", problem=statement)
    assert ExperimentRequest.model_validate_json(request.model_dump_json()) == request
    result = statement.evaluate({"choices": (2.0, 4.0)})
    assert result.feasible and result.objectives == {"loss": 4.0}
    assert not statement.evaluate({"choices": (-1.0, 7.0)}).feasible
    assert not statement.evaluate({"choices": (2.0, 2.0)}).feasible


def test_invalid_references_shapes_and_bounds_rejected():
    original = problem().model_dump()
    for update in (
        {
            "objectives": (
                ObjectiveSpec(name="bad", sense="maximize", expression=Reference(name="missing")),
            )
        },
        {
            "variables": (
                VariableSpec(name="choices", shape="vector", dimension=3, lower=(0.0, 0.0)),
            )
        },
        {"variables": (VariableSpec(name="choices", shape="scalar", lower=3.0, upper=1.0),)},
    ):
        with pytest.raises(ValueError):
            ProblemStatement.model_validate({**original, **update})
    with pytest.raises(ValueError):
        problem().evaluate({"choices": (1.0,)})
    with pytest.raises(ValueError):
        problem().evaluate({"choices": (float("nan"), 1.0)})


def test_expression_language_cannot_execute_code():
    with pytest.raises(ValidationError):
        Operation(operator="eval", arguments=(Constant(value=1.0),))
    with pytest.raises(ValidationError):
        Reference(name="__import__('os')")
    with pytest.raises(ValidationError):
        Operation(operator="dot", arguments=(Constant(value=1.0),))


def test_scalar_integer_problem_and_constraint_relations():
    statement = ProblemStatement(
        description="Integer resource count",
        variables=(VariableSpec(name="count", shape="scalar", domain="integer", lower=0.0),),
        objectives=(
            ObjectiveSpec(name="value", sense="maximize", expression=Reference(name="count")),
        ),
        constraints=(
            ConstraintSpec(
                name="cap", left=Reference(name="count"), relation="le", right=Constant(value=3.0)
            ),
        ),
    )
    assert statement.evaluate({"count": 2.0}).feasible
    assert not statement.evaluate({"count": 2.5}).feasible
    assert not statement.evaluate({"count": 4.0}).feasible


def test_old_unstructured_requests_still_work():
    assert ExperimentRequest(hypothesis="An incomplete future experiment").problem is None
