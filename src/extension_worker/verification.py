"""Container-only execution of declared verification capabilities."""

import importlib

from agent_tools.checks import VerificationCheck, standard_checks
from agent_tools.specs import BundleManifest, VerificationFinding
from agent_tools.verification import verify_problem_result
from simulation_core.execution import JobResult
from simulation_core.registry import ComponentRegistry
from simulation_core.solver import BestResponseGameView, FiniteGameView, Solver
from simulation_core.types import SimulationConfig, WorldState


def benchmark_preflight(
    artifact_config: SimulationConfig, registry: ComponentRegistry, state: WorldState
) -> None:
    spec = artifact_config.benchmark
    if spec is None:
        return
    mechanism = registry.mechanisms[artifact_config.mechanism_id]()
    view = registry.game_views[spec.game_view_id](
        artifact_config.model_copy(deep=True), state.model_copy(deep=True), mechanism
    )
    solver = registry.solvers[spec.solver_id]()
    if (
        not isinstance(view, (FiniteGameView, BestResponseGameView))
        and type(solver).best_responses is Solver.best_responses
    ):
        raise TypeError("Benchmark diagnostics require finite actions or a best-response oracle")


def assess(
    artifact: JobResult, bundle: BundleManifest, registry: ComponentRegistry
) -> tuple[VerificationFinding, ...]:
    from .runtime import require_container

    require_container()
    findings = []
    try:
        verify_problem_result(artifact, bundle.verification)
        findings.append(
            VerificationFinding(
                id="recorded_problem",
                status="verified"
                if artifact.manifest.request.problem is not None
                and artifact.manifest.request.problem.evaluation == "deterministic"
                else "unverified",
                evidence="Problem-derived recorded-profile check; see applicability of selected custom checks",
                required=artifact.manifest.request.problem is not None
                and artifact.manifest.request.problem.evaluation == "deterministic",
            )
        )
    except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
        findings.append(
            VerificationFinding(id="recorded_problem", status="failed", evidence=str(exc))
        )
    findings.extend(standard_checks(artifact, registry, bundle.verification))
    if bundle.verification is not None:
        for specification in bundle.verification.custom_checks:
            try:
                module, name = specification.symbol.split(":")
                implementation = getattr(importlib.import_module(module), name)
                if not isinstance(implementation, type) or not issubclass(
                    implementation, VerificationCheck
                ):
                    raise TypeError("Custom checker must implement VerificationCheck")
                finding = VerificationFinding.model_validate(
                    implementation().assess(artifact.model_copy(deep=True), registry).model_dump()
                )
                findings.append(
                    finding.model_copy(
                        update={"id": specification.id, "required": specification.required}
                    )
                )
            except (ValueError, TypeError, AttributeError, KeyError, ArithmeticError) as exc:
                findings.append(
                    VerificationFinding(
                        id=specification.id,
                        status="failed",
                        evidence=str(exc),
                        required=specification.required,
                    )
                )
    return tuple(findings)
