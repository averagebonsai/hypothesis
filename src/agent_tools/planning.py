"""Static pre-freeze checks. Generated tests are parsed/linted, never imported here."""

import ast
import json
import sys
from math import isclose
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from components.library import standard_registry
from simulation_core.execution import JobManifest
from simulation_core.request import ExperimentRequest

from .inventory import compatibility_findings, inventory
from .jobs import ToolJobManifest
from .process import bounded_command
from .specs import BundleManifest
from .test_intent import fixture_issues

if TYPE_CHECKING:
    from .authoring import CodingPlan


def test_structure_issues(sources: dict[str, str], manifest: BundleManifest) -> list[str]:
    """A conservative dependency check, not a proof of semantic test adequacy."""
    issues = []
    found = set()
    modules = {component.symbol.split(":")[0] for component in manifest.components}
    if not modules:
        modules.update(
            {"components.library", "simulation_core.execution", "simulation_core.runtime"}
        )
    for path, source in sources.items():
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError as exc:
            issues.append(f"{path}: {exc}")
            continue
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in modules:
                imports.update(alias.asname or alias.name for alias in node.names)
            if isinstance(node, ast.Import):
                imports.update(
                    alias.asname or alias.name.split(".")[0]
                    for alias in node.names
                    if alias.name in modules
                )
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}

        def exercises_component(
            name: str,
            visited: frozenset[str] = frozenset(),
            *,
            functions: dict[str, ast.FunctionDef] = functions,
            imports: set[str] = imports,
        ) -> bool:
            if name in visited or name not in functions:
                return False
            function = functions[name]
            # Fixture dependencies are function arguments; helpers are explicit calls.
            names = {arg.arg for arg in function.args.args}
            names.update(node.id for node in ast.walk(function) if isinstance(node, ast.Name))
            calls = [node.func for node in ast.walk(function) if isinstance(node, ast.Call)]
            roots = set()
            for call in calls:
                while isinstance(call, ast.Attribute):
                    call = call.value
                if isinstance(call, ast.Name):
                    roots.add(call.id)
            return bool(roots & imports) or any(
                exercises_component(helper, visited | {name}, functions=functions, imports=imports)
                for helper in names & functions.keys()
            )

        for name, function in functions.items():
            if name.startswith("test_"):
                found.add(name)
                if not exercises_component(name):
                    issues.append(
                        f"{path}:{name}: must exercise an exported component, directly or through a helper/fixture"
                    )
                nodes = tuple(ast.walk(function))
                if not any(isinstance(node, ast.Assert) for node in nodes) and not any(
                    isinstance(node, ast.Attribute) and node.attr == "raises" for node in nodes
                ):
                    issues.append(f"{path}:{name}: needs an assertion or an expected exception")
    required = {
        case.name for component in manifest.components for case in component.acceptance_tests
    }
    issues.extend(f"Missing declared test: {name}" for name in sorted(required - found))
    return issues


def schema_claim_issues(manifest: BundleManifest) -> tuple[str, ...]:
    issues: list[str] = []
    for component in manifest.components:
        for schema_document in (component.input_schema, component.output_schema):
            if schema_document is not None and not set(schema_document) & {
                "type",
                "$ref",
                "anyOf",
                "oneOf",
                "allOf",
                "enum",
                "const",
            }:
                issues.append(
                    f"{component.id}: schema must express a type/constraint; prefer a Pydantic model reference"
                )
    return tuple(issues)


def review_plan(
    project: Path, request: ExperimentRequest, experiment_id: str, plan: "CodingPlan"
) -> tuple[str, ...]:
    if request.execution_kind != "auto" and plan.kind != request.execution_kind:
        return ("Authoring route contradicts the user's requested execution kind",)
    if plan.kind == "tool":
        issues = list(schema_claim_issues(plan.bundle))
        try:
            assert plan.tool is not None
            ToolJobManifest(request=request, tool=plan.tool)
        except ValueError as exc:
            issues.append(str(exc))
        if plan.bundle.experiment_id != experiment_id or plan.bundle.version != "v1":
            issues.append("Plan namespace/version mismatch")
        if not plan.bundle.gap_analysis.ready:
            issues.append("Resolve unsupported tool requirements before implementation")
        if any(
            component.kind not in {"utility", "parameter_schema"}
            for component in plan.bundle.components
        ):
            issues.append(
                "Direct computation uses callable/schema components, not simulation components"
            )
        if plan.bundle.notebook is not None:
            issues.append(
                "Simulation notebook generators require a simulation; direct tools may provide a separate reporting utility"
            )
        return tuple(issues) + review_tests(project, plan)

    try:
        manifest = plan.bundle
        config = plan.simulation
        if config is None:
            return ("Missing simulation configuration",)
        JobManifest(request=request, simulation=config)
    except ValueError as exc:
        return (str(exc),)
    issues = list(compatibility_findings(manifest.gap_analysis)) + list(
        schema_claim_issues(manifest)
    )
    if manifest.experiment_id != experiment_id or manifest.version != "v1":
        issues.append("Plan namespace/version mismatch")
    if not manifest.gap_analysis.ready:
        issues.append("Resolve critical unknowns/unsupported requirements before freezing")
    if manifest.notebook is None:
        issues.append("Declare a notebook generator for the results report")
    known = inventory()
    registry = standard_registry()
    selections = [
        (config.protocol_id, config.protocol_parameters),
        (config.mechanism_id, config.world.parameters),
        *((actor.policy_id, actor.policy_parameters) for actor in config.world.actors),
    ]
    if config.benchmark is not None:
        selections.append((config.benchmark.solver_id, config.benchmark.parameters))
    for identifier, parameters in selections:
        schema = registry.parameter_schemas.get(identifier)
        if schema is not None:
            try:
                schema.model_validate_json(json.dumps(parameters, allow_nan=False))
            except ValueError as exc:
                issues.append(f"Invalid parameters for {identifier}: {exc}")
    tables = {
        "mechanism": "mechanisms",
        "protocol": "protocols",
        "policy": "policies",
        "action_schema": "action_schemas",
        "game_view": "game_views",
        "solver": "solvers",
        "parameter_schema": "parameter_schemas",
    }
    # Registry discovery uses these tables; concrete preflight still runs in Docker.
    for kind, identifier in (
        ("mechanism", config.mechanism_id),
        ("protocol", config.protocol_id),
        *(("policy", actor.policy_id) for actor in config.world.actors),
        *(
            ("action_schema", schema)
            for actor in config.world.actors
            for schema in actor.action_space.schemas.values()
        ),
        *(
            ([("solver", config.benchmark.solver_id), ("game_view", config.benchmark.game_view_id)])
            if config.benchmark
            else []
        ),
    ):
        exports = {component.id for component in manifest.components if component.kind == kind}
        entries = known.get(tables[kind], {})
        if identifier not in exports and (
            not isinstance(entries, (dict, list)) or identifier not in entries
        ):
            issues.append(f"Unknown {kind} binding: {identifier}")
    if request.problem is not None:
        verification = manifest.verification
        if verification is None:
            issues.append("Structured problems require variable/objective verification bindings")
        else:
            problem = request.problem
            if {b.variable for b in verification.variables} != {
                v.name for v in problem.variables
            } or len(verification.variables) != len(problem.variables):
                issues.append("Verification must bind every problem variable exactly once")
            if {b.objective for b in verification.objectives} != {
                o.name for o in problem.objectives
            } or len(verification.objectives) != len(problem.objectives):
                issues.append("Verification must bind every problem objective exactly once")
            for binding in verification.variables:
                owners = {v.actor_id for v in problem.variables if v.name == binding.variable}
                if binding.actor_id not in {a.id for a in config.world.actors} or (
                    owners - {None} and binding.actor_id not in owners
                ):
                    issues.append(f"Incorrect variable owner: {binding.variable}")
            for objective_binding in verification.objectives:
                objective = next(
                    (o for o in problem.objectives if o.name == objective_binding.objective), None
                )
                if (
                    objective
                    and objective_binding.source == "payoff"
                    and objective.actor_id is not None
                    and objective_binding.key != objective.actor_id
                ):
                    issues.append(
                        f"Incorrect objective payoff owner: {objective_binding.objective}"
                    )
            if not verification.reference_cases and problem.evaluation == "deterministic":
                issues.append(
                    "Declare grounded reference cases before freezing the numeric verification intent"
                )
            for case in verification.reference_cases:
                try:
                    evaluated = problem.evaluate(case.assignments)
                    if evaluated.feasible != case.feasible:
                        issues.append(
                            f"Reference case {case.id}: expected feasibility contradicts the problem"
                        )
                    if case.feasible and set(case.objectives) != set(evaluated.objectives):
                        issues.append(
                            f"Reference case {case.id}: provide all objective expectations"
                        )
                    for name, value in case.objectives.items():
                        if name not in evaluated.objectives or not isclose(
                            value,
                            evaluated.objectives[name],
                            rel_tol=verification.tolerance,
                            abs_tol=verification.tolerance,
                        ):
                            issues.append(
                                f"Reference case {case.id}: objective {name} contradicts the problem definition"
                            )
                    if case.violations and set(case.violations) != set(evaluated.violations):
                        issues.append(
                            f"Reference case {case.id}: violation names contradict the problem"
                        )
                except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
                    issues.append(f"Reference case {case.id}: {exc}")
            if verification.action_behavior == "custom" and not any(
                check.required for check in verification.custom_checks
            ):
                issues.append(
                    "Custom action behavior requires a required applicable custom checker"
                )
            if verification.parameter_cases and problem.evaluation != "deterministic":
                issues.append(
                    "Numeric parameter cases need deterministic evaluation; use custom checks for this domain"
                )
            for parameter_case in verification.parameter_cases:
                try:
                    if set(parameter_case.parameters) - problem.parameters.keys():
                        raise ValueError("Unknown parameter override")
                    changed = type(problem).model_validate(
                        problem.model_copy(
                            update={
                                "parameters": {**problem.parameters, **parameter_case.parameters}
                            }
                        ).model_dump()
                    )
                    if not changed.evaluate(parameter_case.assignments).feasible:
                        issues.append(
                            f"Parameter case {parameter_case.id}: use a feasible assignment; rejection belongs in a rejection case"
                        )
                except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
                    issues.append(f"Parameter case {parameter_case.id}: {exc}")
            if problem.evaluation != "deterministic" and not any(
                check.required for check in verification.custom_checks
            ):
                issues.append("Declare a required custom checker for non-deterministic evaluation")
            if (
                problem.evaluation == "deterministic"
                and config.benchmark
                and len(problem.objectives) == 1
                and all(v.domain == "continuous" for v in problem.variables)
                and verification.independent_reference != "single_objective_slsqp"
            ):
                issues.append(
                    "This supported single-objective continuous benchmark requires the independent numerical reference"
                )
    return tuple(issues) + review_tests(project, plan)


def review_tests(project: Path, plan: "CodingPlan") -> tuple[str, ...]:
    from .authoring import safe_source_path

    issues: list[str] = []
    manifest = plan.bundle
    sources = {source.path: source.content for source in plan.tests}
    if len(sources) != len(plan.tests) or any(
        not safe_source_path(path, tests=True) for path in sources
    ):
        return (*issues, "Tests need unique safe Python paths under tests/")
    issues.extend(test_structure_issues(sources, manifest))
    for path, content in sources.items():
        issues.extend(fixture_issues(content, path))
    with TemporaryDirectory(prefix="authoring-plan-") as temporary:
        root = Path(temporary)
        for path, content in sources.items():
            destination = root / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content)
        result = bounded_command(
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "--config",
                str(project / "pyproject.toml"),
                str(root),
            ],
            seconds=30,
            max_bytes=100_000,
        )
        if result.code:
            issues.append("Test lint failed:\n" + result.stdout + result.stderr)
    return tuple(issues)
