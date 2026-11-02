"""Discoverable method requirements and evidence; sampled tests are not proofs."""

from typing import Literal, Self

from pydantic import Field, model_validator

from .types import FrozenModel


class MethodRequirement(FrozenModel):
    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    enforcement: Literal["required", "conditional"] = "required"


class RequirementEvidence(FrozenModel):
    requirement_id: str
    status: Literal["verified", "violated", "unverified"]
    basis: Literal[
        "runtime_check",
        "model_definition",
        "analytic_argument",
        "declaration",
        "sampled_test",
        "none",
    ] = "none"
    explanation: str = Field(min_length=1)

    @model_validator(mode="after")
    def no_sampled_proofs(self) -> Self:
        if self.status == "verified" and self.basis in {"declaration", "sampled_test", "none"}:
            raise ValueError(
                "Declarations and sampled tests cannot verify a mathematical requirement"
            )
        return self


class MethodContract(FrozenModel):
    name: str = Field(min_length=1)
    requirements: tuple[MethodRequirement, ...] = ()
    guarantees: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def distinct_requirements(self) -> Self:
        ids = [requirement.id for requirement in self.requirements]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate method requirement")
        return self

    def assess(self, evidence: tuple[RequirementEvidence, ...] = ()) -> "ApplicabilityReport":
        checks = {item.requirement_id: item for item in evidence}
        if len(checks) != len(evidence) or set(checks) - {r.id for r in self.requirements}:
            raise ValueError("Evidence must reference distinct declared requirements")
        return ApplicabilityReport(
            contract=self,
            evidence=tuple(
                checks.get(
                    requirement.id,
                    RequirementEvidence(
                        requirement_id=requirement.id,
                        status="unverified",
                        explanation="No verification evidence supplied",
                    ),
                )
                for requirement in self.requirements
            ),
        )


class ApplicabilityError(ValueError):
    pass


class ApplicabilityReport(FrozenModel):
    contract: MethodContract
    evidence: tuple[RequirementEvidence, ...]

    @model_validator(mode="after")
    def complete_evidence(self) -> Self:
        if tuple(item.requirement_id for item in self.evidence) != tuple(
            r.id for r in self.contract.requirements
        ):
            raise ValueError("Report must contain one ordered assessment per requirement")
        return self

    @property
    def can_execute(self) -> bool:
        return all(
            requirement.enforcement != "required" or check.status == "verified"
            for requirement, check in zip(self.contract.requirements, self.evidence)
        )

    @property
    def preconditions_verified(self) -> bool:
        return bool(self.contract.requirements) and all(
            check.status == "verified" for check in self.evidence
        )

    def require_preconditions(self) -> None:
        """Optional strict policy: refuse even unresolved conditional assumptions."""
        if not self.preconditions_verified:
            unresolved = [
                check.requirement_id for check in self.evidence if check.status != "verified"
            ]
            raise ApplicabilityError(
                f"Method preconditions not established: {', '.join(unresolved) or 'no requirements declared'}"
            )

    def require_execution(self) -> None:
        if not self.can_execute:
            blocked = [
                r.id
                for r, check in zip(self.contract.requirements, self.evidence)
                if r.enforcement == "required" and check.status != "verified"
            ]
            raise ApplicabilityError(f"Method requirements not established: {', '.join(blocked)}")


def checked(
    requirement_id: str,
    condition: bool,
    explanation: str,
    *,
    basis: Literal["runtime_check", "model_definition", "analytic_argument"] = "runtime_check",
) -> RequirementEvidence:
    return RequirementEvidence(
        requirement_id=requirement_id,
        status="verified" if condition else "violated",
        basis=basis,
        explanation=explanation,
    )
