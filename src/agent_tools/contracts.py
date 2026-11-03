"""Native authoring documents and explicit terminal outcomes; no embedded JSON strings."""

from typing import Literal, Self

from pydantic import Field, model_validator

from simulation_core.types import FrozenModel, SimulationConfig

from .jobs import ToolInvocation
from .specs import BundleManifest, ReportReceipt, RunReceipt


class SourceFile(FrozenModel):
    path: str
    content: str = Field(max_length=250000)


class CodingPlan(FrozenModel):
    summary: str = Field(min_length=1, max_length=3000)
    bundle: BundleManifest
    kind: Literal["agent_simulation", "tool"] = "agent_simulation"
    simulation: SimulationConfig | None = None
    tool: ToolInvocation | None = None
    tests: tuple[SourceFile, ...] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def correct_route(self) -> Self:
        if self.kind == "tool":
            if self.tool is None or self.simulation is not None:
                raise ValueError("Direct tools need an invocation and no simulation scaffold")
        elif self.simulation is None or self.tool is not None:
            raise ValueError(
                "Agent simulations need a SimulationConfig and no direct-tool invocation"
            )
        return self


class Implementation(FrozenModel):
    summary: str = Field(min_length=1, max_length=3000)
    files: tuple[SourceFile, ...] = Field(min_length=1, max_length=40)


class AuthoredCandidate(FrozenModel):
    """A complete offline candidate; no separate prototype-to-implementation handoff."""

    plan: CodingPlan
    implementation: Implementation


class NotebookReview(FrozenModel):
    approved: bool
    issues: tuple[str, ...] = ()

    @model_validator(mode="after")
    def consistent_review(self) -> Self:
        if self.approved == bool(self.issues):
            raise ValueError("Approve only when there are no outstanding issues")
        return self


class ReviewRequest(FrozenModel):
    status: Literal["needs_review", "unsupported"]
    reason: str = Field(min_length=1)
    affected_contracts: tuple[str, ...] = Field(min_length=1)


class PlanningResponse(FrozenModel):
    plan: CodingPlan | None
    review: ReviewRequest | None

    @model_validator(mode="after")
    def one_outcome(self) -> Self:
        if (self.plan is None) == (self.review is None):
            raise ValueError("Return exactly one plan or review request")
        return self


class ImplementationResponse(FrozenModel):
    implementation: Implementation | None
    review: ReviewRequest | None

    @model_validator(mode="after")
    def one_outcome(self) -> Self:
        if (self.implementation is None) == (self.review is None):
            raise ValueError("Return exactly one implementation or review request")
        return self


class CandidateResponse(FrozenModel):
    candidate: AuthoredCandidate | None
    review: ReviewRequest | None

    @model_validator(mode="after")
    def one_outcome(self) -> Self:
        if (self.candidate is None) == (self.review is None):
            raise ValueError("Return exactly one complete candidate or review request")
        return self


class AuthoringOutcome(FrozenModel):
    status: Literal["completed", "needs_review", "unsupported"]
    receipt: RunReceipt | None = None
    review: ReviewRequest | None = None
    candidate: str | None = None
    report_receipt: ReportReceipt | None = None
    report_candidate: str | None = None
    report_output: str | None = None

    @model_validator(mode="after")
    def consistent_status(self) -> Self:
        if self.report_receipt is not None and (
            not self.report_receipt.response.passed
            or self.report_candidate is None
            or self.report_output is None
        ):
            raise ValueError("A revised report requires validated report provenance")
        if self.status == "completed":
            if (
                self.review is not None
                or self.receipt is None
                or (
                    self.receipt.response.result is None
                    and self.receipt.response.tool_result is None
                )
                or not self.receipt.response.passed
            ):
                raise ValueError("Completion requires a fully validated result")
        elif self.review is None or self.review.status != self.status:
            raise ValueError("Review outcome needs a matching review request")
        return self
