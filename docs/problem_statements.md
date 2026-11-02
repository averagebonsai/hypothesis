# Structured user problems

`simulation_core.problems.ProblemStatement` is an optional, typed part of
`ExperimentRequest.problem`. Previously requests provided prose, requirements,
and supplied values with optional configuration paths; they did not provide a
formal objective/constraint language.

The new Pydantic models describe actors, named scalar/vector parameters, owned or
unowned decision variables, continuous/integer domains, bounds, objective senses,
and equality/inequality constraints. A vector dimension can be a fixed integer or
the name of a vector parameter. Objectives may belong to different actors.
Timing, evaluation type, and additional requirements remain explicit fields.

Expressions are tagged data: `Constant`, `Reference`, and `Operation` support
addition, subtraction, scalar multiplication, dot products, summation, elementwise
squaring, and negation. There is no Python evaluation or arbitrary callable in a
user problem. References, dimensions, scalar objectives/constraints, ownership,
duplicate names, finite values, and bound consistency are validated before coding.

For example, this describes a linear program without choosing a solution method:

```python
from simulation_core.problems import (
    Constant, ConstraintSpec, ObjectiveSpec, Operation, ProblemStatement,
    Reference, VariableSpec,
)
from simulation_core.request import ExperimentRequest

problem = ProblemStatement(
    description="Choose nonnegative production quantities within a resource cap",
    parameters={"prices": (3.0, 2.0), "resource": (2.0, 1.0), "capacity": 8.0},
    variables=(VariableSpec(name="production", shape="vector", dimension="prices", lower=0.0),),
    objectives=(ObjectiveSpec(
        name="revenue", sense="maximize",
        expression=Operation(operator="dot", arguments=(
            Reference(name="prices"), Reference(name="production"),
        )),
    ),),
    constraints=(ConstraintSpec(
        name="resource_cap", relation="le",
        left=Operation(operator="dot", arguments=(
            Reference(name="resource"), Reference(name="production"),
        )),
        right=Reference(name="capacity"),
    ),),
)
request = ExperimentRequest(hypothesis="Which production mix maximizes revenue?", problem=problem)
transport_json = request.model_dump_json()
restored = ExperimentRequest.model_validate_json(transport_json)
evaluation = problem.evaluate({"production": (2.0, 3.0)})
assert evaluation.feasible and evaluation.objectives["revenue"] == 12.0
```

`evaluate` returns objective values, signed constraint residuals (left minus
right), and feasibility violations for an assignment. It does not optimize,
certify convexity, prove feasibility of the full problem, or select a method.
The coding agent still analyzes compatibility and maps this statement into an
experiment configuration, mechanism, and appropriate solver. The request preserves
the original statement beside the resolved configuration. This interface supports
simplex-constrained allocations and small linear/quadratic formulations; it does
not implement the simplex optimization algorithm. General nonlinear functions,
matrices, distributions, and symbolic proofs need future explicit extensions.

Existing prose-only requests continue to work. JSON schema is available through
`ExperimentRequest.model_json_schema()`; Python tuple fields serialize as arrays.
Use `model_validate_json` or `from_json_values` at JSON boundaries.
