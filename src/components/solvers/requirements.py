"""Shared game-solver declarations; external mathematical claims default to unknown."""

from simulation_core.contracts import MethodRequirement, RequirementEvidence

VIEW = MethodRequirement(
    id="view", description="The solver's declared game-view capability is available"
)
PURE_PAYOFFS = MethodRequirement(
    id="pure_payoffs",
    enforcement="conditional",
    description="Evaluation is deterministic, side-effect-free, finite, and returns every actor's payoff for each feasible profile",
)


def model_evidence(
    requirement_id: str, standard_implementation: bool, explanation: str
) -> RequirementEvidence:
    return RequirementEvidence(
        requirement_id=requirement_id,
        status="verified" if standard_implementation else "unverified",
        basis="model_definition" if standard_implementation else "none",
        explanation=explanation
        if standard_implementation
        else "Custom implementation: model-specific justification has not been established",
    )
