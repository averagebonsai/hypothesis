"""Problem-derived checks independent of an extension's scoring and solver code."""

from collections.abc import Sequence
from math import isclose

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import NonlinearConstraint, minimize

from simulation_core.execution import JobResult
from simulation_core.problems import Numeric, ProblemStatement
from simulation_core.types import Action, Outcome

from .specs import VerificationSpec


def assignments_for(actions: Sequence[Action], spec: VerificationSpec) -> dict[str, Numeric]:
    by_actor = {action.actor_id: action for action in actions}
    assignments: dict[str, Numeric] = {}
    for binding in spec.variables:
        raw = by_actor[binding.actor_id].payload[binding.payload_field]
        if (
            isinstance(raw, list)
            and raw
            and all(isinstance(x, (float, int)) and not isinstance(x, bool) for x in raw)
        ):
            assignments[binding.variable] = tuple(float(x) for x in raw)  # type: ignore[arg-type]
        elif isinstance(raw, (float, int)) and not isinstance(raw, bool):
            assignments[binding.variable] = float(raw)
        else:
            raise ValueError(f"Non-numeric variable binding: {binding.variable}")
    return assignments


def independent_optimum(problem: ProblemStatement, initial: dict[str, Numeric]) -> float:
    """Multistart numerical reference, not a global-optimality certificate."""
    if len(problem.objectives) != 1 or any(v.domain != "continuous" for v in problem.variables):
        raise ValueError("Independent SLSQP supports continuous single-objective problems only")
    sizes = [problem.dimension(v) if v.shape == "vector" else 1 for v in problem.variables]
    bounds: list[tuple[float | None, float | None]] = []
    start: list[float] = []
    for variable, size in zip(problem.variables, sizes):
        value = initial[variable.name]
        start.extend(value if isinstance(value, tuple) else (value,))
        lower = variable.lower if isinstance(variable.lower, tuple) else (variable.lower,) * size
        upper = variable.upper if isinstance(variable.upper, tuple) else (variable.upper,) * size
        bounds.extend(zip(lower, upper))

    def unpack(values: NDArray[np.float64]) -> dict[str, Numeric]:
        result: dict[str, Numeric] = {}
        offset = 0
        for variable, size in zip(problem.variables, sizes):
            coordinates = tuple(float(x) for x in values[offset : offset + size])
            result[variable.name] = coordinates if variable.shape == "vector" else coordinates[0]
            offset += size
        return result

    objective = problem.objectives[0]
    sign = -1 if objective.sense == "maximize" else 1

    def score(values: NDArray[np.float64]) -> float:
        return sign * problem.evaluate(unpack(values)).objectives[objective.name]

    constraints: list[NonlinearConstraint] = []
    for constraint in problem.constraints:

        def residual(
            values: NDArray[np.float64],
            name: str = constraint.name,
            multiplier: int = -1 if constraint.relation == "le" else 1,
        ) -> NDArray[np.float64]:
            return np.array(
                [multiplier * problem.evaluate(unpack(values)).constraint_residuals[name]]
            )

        constraints.append(
            NonlinearConstraint(residual, 0.0, 0.0 if constraint.relation == "eq" else np.inf)
        )
    candidates = []
    for seed in (np.array(start, dtype=np.float64), np.zeros(len(start)), np.ones(len(start))):
        result = minimize(
            score,
            seed,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"ftol": 1e-12, "maxiter": 1000},
        )
        if result.success and problem.evaluate(unpack(result.x)).feasible:
            candidates.append(float(result.fun))
    if not candidates:
        raise ValueError("Independent reference did not converge to a feasible solution")
    return sign * min(candidates)


def verify_profile(
    problem: ProblemStatement, spec: VerificationSpec, actions: Sequence[Action], outcome: Outcome
) -> dict[str, Numeric]:
    assignment = assignments_for(actions, spec)
    evaluated = problem.evaluate(assignment)
    if not evaluated.feasible:
        raise ValueError(f"Problem feasibility failed: {evaluated.violations}")
    for binding in spec.objectives:
        reported = outcome.payoffs if binding.source == "payoff" else outcome.metrics
        value = reported[binding.key]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isclose(
                float(value),
                binding.scale * evaluated.objectives[binding.objective],
                rel_tol=spec.tolerance,
                abs_tol=spec.tolerance,
            )
        ):
            raise ValueError(f"Objective mismatch: {binding.objective}")
    return assignment


def verify_problem_result(artifact: JobResult, spec: VerificationSpec | None) -> None:
    problem = artifact.manifest.request.problem
    if problem is None:
        return
    if spec is None:
        raise ValueError("Structured problem needs verification bindings")
    if problem.evaluation != "deterministic":
        if not any(check.required for check in spec.custom_checks):
            raise ValueError(
                "Non-deterministic problems require an applicable required custom checker"
            )
        return

    def check(actions: Sequence[Action], outcome: Outcome) -> dict[str, Numeric]:
        return verify_profile(problem, spec, actions, outcome)

    latest = {}
    checked = 0
    required_actors = {binding.actor_id for binding in spec.variables}
    scripted = {
        actor.id: actor.policy_parameters
        for actor in artifact.manifest.simulation.world.actors
        if actor.policy_id == "scripted.v1"
    }
    for event in artifact.result.events:
        for action in event.actions:
            if action.actor_id in scripted:
                parameters = scripted[action.actor_id]
                if action.payload != parameters["payload"] or action.kind != parameters["kind"]:
                    raise ValueError("Primary scripted action was replaced")
            latest[action.actor_id] = action
        if event.outcome is not None and required_actors <= latest.keys():
            check(tuple(latest.values()), event.outcome)
            checked += 1
    if not checked:
        raise ValueError("No complete primary profile was checked")
    if artifact.manifest.simulation.benchmark is not None:
        benchmark = artifact.benchmark
        if (
            benchmark is None
            or benchmark.comparison_status != "complete"
            or not benchmark.result.equilibria
        ):
            raise ValueError("Requested benchmark is unavailable or has no solution to verify")
        for solution in benchmark.result.equilibria:
            assignment = check(solution.actions, solution.outcome)
            if spec.independent_reference == "single_objective_slsqp":
                value = problem.evaluate(assignment).objectives[problem.objectives[0].name]
                reference = independent_optimum(problem, assignment)
                if not isclose(value, reference, rel_tol=spec.tolerance, abs_tol=spec.tolerance):
                    raise ValueError("Benchmark disagrees with independent numerical reference")
