"""Curated discovery metadata, not an automatic scientific problem classifier."""

from typing import get_args

from pydantic import JsonValue

from components.common.economics.models import LinearDemand, LinearInverseDemand
from components.common.math.scalar import SCALAR_SEARCH_CONTRACT
from components.library import standard_registry

from .specs import GapAnalysisReport, PythonDistribution

SHAPES = {
    "pure_nash.v1": ("finite",),
    "textbook_bertrand.v1": ("scalar",),
    "numerical_nash.v1": ("scalar",),
    "backward_induction.v1": ("scalar",),
    "normal_form.v1": ("finite",),
    "homogeneous_bertrand.v1": ("scalar",),
    "differentiated_bertrand.v1": ("scalar",),
    "stackelberg.v1": ("scalar",),
    "components.common.math.scalar.maximize_scalar": ("scalar",),
}


def inventory() -> dict[str, JsonValue]:
    result = standard_registry().describe()
    # Discoverable even when this host has not enabled live execution. The worker
    # still requires an explicitly supplied host relay before binding this policy.
    result["policies"] = ["scripted.v1", "llm.v1"]
    result["decision_shapes_per_actor"] = {key: list(value) for key, value in SHAPES.items()}
    result["shared_tools"] = {
        "components.common.math.scalar.maximize_scalar": {
            "constraints": "One finite interval, no coupled vector constraints",
            "contract": SCALAR_SEARCH_CONTRACT.model_dump(mode="json"),
        },
        "components.common.economics.models.LinearDemand": LinearDemand.model_json_schema(),
        "components.common.economics.models.LinearInverseDemand": LinearInverseDemand.model_json_schema(),
        "simulation_core.reporting.write_results_notebook": {
            "signature": "(artifact: JobResult, directory: Path) -> Path",
            "purpose": "Write results.ipynb; the worker supplies result.json and executes the notebook",
        },
    }
    result["limitations"] = [
        "Metadata is curated; absent metadata is unknown, not proof of compatibility",
        "llm.v1 requires host-enabled actor relay; disabled unless the operator supplies actor_gateway and actor_model to DockerWorker. Credentials stay on the host.",
    ]
    result["approved_python_distributions"] = list(get_args(PythonDistribution))
    result["task_routes"] = {
        "tool": "Pure callable + tests; no actors, protocol, mechanism, GameView or Nash wrapper",
        "agent_simulation": "Policies + authorized observations + mechanism + protocol + runtime; mathematical analysis is separate",
    }
    result["verification_capabilities"] = {
        "reject_infeasible": "Opt-in deterministic complete-profile bounds/constraint/shape counterexamples",
        "parameter_cases": "Declared numeric parameter variations of mechanism/solver, without actor calls",
        "custom_checks": "VerificationCheck subclasses; report applicability and evidence; stochastic/stateful domains need suitable custom checks",
    }
    result["benchmark_requirements"] = (
        "Current BenchmarkRunner diagnostics require finite actions, a best-response view, or solver-supplied best responses"
    )
    return result


def compatibility_findings(report: GapAnalysisReport) -> tuple[str, ...]:
    findings = []
    for decision in report.decisions:
        if decision.disposition not in {"REUSE", "COMPOSE"}:
            continue
        for component in decision.selected_components:
            supported = SHAPES.get(component)
            shape = decision.requirement.action_shape
            if supported and shape != "unknown" and shape not in supported:
                findings.append(
                    f"{decision.requirement.id}: {component} supports {supported} per actor, not {shape}"
                )
            if shape == "scalar" and any(
                dimension != 1 for dimension in decision.requirement.dimensions_per_actor.values()
            ):
                findings.append(
                    f"{decision.requirement.id}: scalar decisions require dimension 1 per actor"
                )
    return tuple(dict.fromkeys(findings))
