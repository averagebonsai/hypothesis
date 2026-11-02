"""Curated discovery metadata, not an automatic scientific problem classifier."""

from pydantic import JsonValue

from components.common.economics.models import LinearDemand, LinearInverseDemand
from components.common.math.scalar import SCALAR_SEARCH_CONTRACT
from components.library import standard_registry

from .specs import GapAnalysisReport

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
    result["decision_shapes_per_actor"] = {key: list(value) for key, value in SHAPES.items()}
    result["shared_tools"] = {
        "components.common.math.scalar.maximize_scalar": {
            "constraints": "One finite interval, no coupled vector constraints",
            "contract": SCALAR_SEARCH_CONTRACT.model_dump(mode="json"),
        },
        "components.common.economics.models.LinearDemand": LinearDemand.model_json_schema(),
        "components.common.economics.models.LinearInverseDemand": LinearInverseDemand.model_json_schema(),
    }
    result["limitations"] = [
        "Metadata is curated; absent metadata is unknown, not proof of compatibility",
        "LLM policies require gateway injection and are disabled in offline extension workers",
    ]
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
