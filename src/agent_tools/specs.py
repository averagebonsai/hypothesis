"""Data-only contracts for an external coding agent's extension workflow."""

from typing import Literal, Self

from pydantic import Field, JsonValue, model_validator

from simulation_core.contracts import MethodContract
from simulation_core.execution import JobResult
from simulation_core.problems import Numeric
from simulation_core.types import FrozenModel

from .jobs import ToolResult

ComponentKind = Literal[
    "policy",
    "mechanism",
    "protocol",
    "solver",
    "game_view",
    "action_schema",
    "parameter_schema",
    "utility",
]
PARENTS = {
    "policy": "simulation_core.policy.Policy",
    "mechanism": "simulation_core.mechanism.Mechanism",
    "protocol": "simulation_core.protocol.ProtocolRules",
    "solver": "simulation_core.solver.Solver",
    "game_view": "simulation_core.solver.GameView",
    "action_schema": "pydantic.BaseModel",
    "parameter_schema": "pydantic.BaseModel",
    "utility": "typing.Callable",
}

# Packages already present in the locked worker image, including reporting tools.
PythonDistribution = Literal[
    "numpy", "scipy", "pydantic", "python-dotenv", "matplotlib", "nbformat", "nbclient", "ipykernel"
]


class NotebookSpec(FrozenModel):
    report_version: Literal["explanatory.v1"] | None = None
    preview_generator: str | None = Field(
        default=None,
        pattern=r"^experiment_extension(?:\.[A-Za-z_][A-Za-z0-9_]*)+:[A-Za-z_][A-Za-z0-9_]*$",
        description="Offline callable (JobManifest, Path) -> Path writing preview.ipynb; no observed results",
    )
    generator: str = Field(
        pattern=r"^experiment_extension(?:\.[A-Za-z_][A-Za-z0-9_]*)+:[A-Za-z_][A-Za-z0-9_]*$",
        description="Callable (JobResult, output_directory: Path) -> Path writing results.ipynb",
    )


class VariableBinding(FrozenModel):
    variable: str
    actor_id: str
    payload_field: str


class ObjectiveBinding(FrozenModel):
    objective: str
    source: Literal["payoff", "metric"]
    key: str
    scale: Literal[-1, 1] = 1


class ReferenceCase(FrozenModel):
    id: str = Field(min_length=1)
    assignments: dict[str, Numeric]
    feasible: bool
    objectives: dict[str, float] = Field(default_factory=dict)
    # Names from the original ProblemStatement, never arbitrary exception text.
    violations: tuple[str, ...] = ()


class ParameterCase(FrozenModel):
    id: str = Field(min_length=1)
    parameters: dict[str, Numeric]
    assignments: dict[str, Numeric]


class CustomCheckSpec(FrozenModel):
    id: str = Field(min_length=1)
    symbol: str = Field(
        pattern=r"^experiment_extension(?:\.[A-Za-z_][A-Za-z0-9_]*)+:[A-Za-z_][A-Za-z0-9_]*$"
    )
    required: bool = False
    purpose: str = Field(min_length=1)


class VerificationFinding(FrozenModel):
    id: str
    status: Literal["verified", "failed", "unverified", "unsupported"]
    evidence: str
    required: bool = True


class VerificationSpec(FrozenModel):
    variables: tuple[VariableBinding, ...] = ()
    objectives: tuple[ObjectiveBinding, ...] = ()
    independent_reference: Literal["none", "single_objective_slsqp"] = "none"
    tolerance: float = Field(default=1e-6, gt=0, le=1e-4)
    reference_cases: tuple[ReferenceCase, ...] = ()
    action_behavior: Literal["reject_infeasible", "custom", "unverified"] = "unverified"
    parameter_cases: tuple[ParameterCase, ...] = ()
    custom_checks: tuple[CustomCheckSpec, ...] = ()


class CapabilityRequirement(FrozenModel):
    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    action_shape: Literal["none", "finite", "scalar", "vector", "mixed", "unknown"]
    dimensions_per_actor: dict[str, int] = Field(default_factory=dict)
    constraints: tuple[str, ...] = ()
    timing: str = "unspecified"
    evaluation: Literal["deterministic", "stochastic", "unknown"] = "unknown"
    required_guarantees: tuple[str, ...] = ()

    @model_validator(mode="after")
    def positive_dimensions(self) -> Self:
        if any(value <= 0 for value in self.dimensions_per_actor.values()):
            raise ValueError("Actor decision dimensions must be positive")
        return self


class CapabilityDecision(FrozenModel):
    requirement: CapabilityRequirement
    disposition: Literal["REUSE", "COMPOSE", "EXTEND", "UNSUPPORTED"]
    selected_components: tuple[str, ...] = ()
    reason: str = Field(min_length=1)
    unresolved: tuple[str, ...] = ()
    unsupported_reason: Literal["missing_information", "interface_gap"] | None = None

    @model_validator(mode="after")
    def classified_reason(self) -> Self:
        if (self.disposition == "UNSUPPORTED") != (self.unsupported_reason is not None):
            raise ValueError("UNSUPPORTED needs a missing-information or interface-gap reason")
        if self.disposition in {"REUSE", "COMPOSE"} and not self.selected_components:
            raise ValueError("Reuse/composition must name existing components")
        return self


class GapAnalysisReport(FrozenModel):
    objective: str = Field(min_length=1)
    decisions: tuple[CapabilityDecision, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self) -> Self:
        ids = [decision.requirement.id for decision in self.decisions]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate capability requirement")
        return self

    @property
    def ready(self) -> bool:
        return not any(d.disposition == "UNSUPPORTED" or d.unresolved for d in self.decisions)


class AcceptanceTest(FrozenModel):
    name: str = Field(pattern=r"^test_[A-Za-z0-9_]+$")
    category: Literal["interface", "functional", "mathematical", "integration", "failure"]
    expected: str = Field(min_length=1)
    reference: str = Field(min_length=1)


class CustomComponentSpec(FrozenModel):
    id: str = Field(pattern=r"^experimental\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_.]*$")
    kind: ComponentKind
    purpose: str = Field(min_length=1)
    gap_id: str
    parent_interface: str = ""
    symbol: str = Field(
        pattern=r"^experiment_extension(?:\.[A-Za-z_][A-Za-z0-9_]*)+:[A-Za-z_][A-Za-z0-9_]*$"
    )
    input_model: str | None = Field(
        default=None,
        pattern=r"^(?:simulation_core|experiment_extension)(?:\.[A-Za-z_][A-Za-z0-9_]*)+:[A-Za-z_][A-Za-z0-9_]*$",
    )
    output_model: str | None = Field(
        default=None,
        pattern=r"^(?:simulation_core|experiment_extension)(?:\.[A-Za-z_][A-Za-z0-9_]*)+:[A-Za-z_][A-Za-z0-9_]*$",
    )
    input_schema: dict[str, JsonValue] | None = None
    output_schema: dict[str, JsonValue] | None = None
    dependencies: tuple[str, ...] = Field(
        default=(), description="Component IDs; Python packages belong in existing_dependencies"
    )
    method_contract: MethodContract | None = None
    mathematical: bool = False
    acceptance_tests: tuple[AcceptanceTest, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def approved_parent(self) -> Self:
        if not self.parent_interface:
            object.__setattr__(self, "parent_interface", PARENTS[self.kind])
        if self.parent_interface != PARENTS[self.kind]:
            raise ValueError("Use the approved parent for the component kind")
        if (self.kind == "solver" or self.mathematical) and self.method_contract is None:
            raise ValueError("Mathematical tools must declare a method contract")
        return self


class BundleManifest(FrozenModel):
    schema_version: Literal["experimental.bundle.v1"] = "experimental.bundle.v1"
    experiment_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: str = Field(pattern=r"^v[1-9][0-9]*$")
    gap_analysis: GapAnalysisReport
    components: tuple[CustomComponentSpec, ...] = ()
    existing_dependencies: tuple[PythonDistribution, ...] = Field(
        default=(), description="Approved installed Python distribution names, never component IDs"
    )
    repair_counts: dict[str, int] = Field(default_factory=dict)
    notebook: NotebookSpec | None = None
    verification: VerificationSpec | None = None

    @model_validator(mode="after")
    def references(self) -> Self:
        exports = [(component.kind, component.id) for component in self.components]
        if len(set(exports)) != len(exports):
            raise ValueError("Duplicate component export")
        gaps = {d.requirement.id for d in self.gap_analysis.decisions if d.disposition == "EXTEND"}
        known = {c.id for c in self.components}
        for component in self.components:
            if component.gap_id not in gaps or not component.id.startswith(
                f"experimental.{self.experiment_id}."
            ):
                raise ValueError("Extension must address an EXTEND gap in its experiment namespace")
            if any(
                dep.startswith("experimental.") and dep not in known
                for dep in component.dependencies
            ):
                raise ValueError("Unknown experimental dependency")
        if any(count < 0 for count in self.repair_counts.values()):
            raise ValueError("Repair counts must be nonnegative")
        return self


class BundleSeal(FrozenModel):
    schema_version: Literal["experimental.seal.v1"] = "experimental.seal.v1"
    files: dict[str, str]
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class WorkerLimits(FrozenModel):
    wall_seconds: int = Field(default=180, ge=10, le=7200)
    memory_mb: int = Field(default=2048, ge=512, le=8192)
    cpus: int = Field(default=2, ge=1, le=4)
    pids: int = Field(default=128, ge=32, le=256)
    output_bytes: int = Field(default=4_000_000, ge=4096, le=16_000_000)


class CheckResult(FrozenModel):
    name: str
    passed: bool
    exit_code: int
    output: str


VALIDATION_CHECKS = frozenset(
    {"ruff", "mypy", "acceptance", "regressions", "declared_acceptance", "composition"}
)


class DiagnosticArtifact(FrozenModel):
    status: Literal["unapproved"] = "unapproved"
    result: JobResult
    notebook: dict[str, JsonValue] | None = None
    findings: tuple[VerificationFinding, ...] = ()


class WorkerResponse(FrozenModel):
    bundle_digest: str
    checks: tuple[CheckResult, ...]
    result: JobResult | None = None
    tool_result: ToolResult | None = None
    probe_results: tuple[JobResult, ...] = ()
    error: str | None = None
    notebook_json: str | None = None
    verification_findings: tuple[VerificationFinding, ...] = ()
    diagnostic: "DiagnosticArtifact | None" = None
    resolved_schemas: dict[str, dict[str, JsonValue]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_checks(self) -> Self:
        names = [check.name for check in self.checks]
        if len(set(names)) != len(names) or set(names) - VALIDATION_CHECKS:
            raise ValueError("Worker checks must be distinct known validation stages")
        if (
            self.result is not None or self.tool_result is not None or self.probe_results
        ) and not self.passed:
            raise ValueError("An experiment result requires all validation stages to pass")
        if self.notebook_json is not None and self.result is None:
            raise ValueError("A results notebook requires the matching experiment result")
        if self.result is not None and self.tool_result is not None:
            raise ValueError("Return one execution kind")
        return self

    @property
    def passed(self) -> bool:
        return (
            {check.name for check in self.checks} == VALIDATION_CHECKS
            and all(check.passed for check in self.checks)
            and self.error is None
            and all(
                not finding.required or finding.status == "verified"
                for finding in self.verification_findings
            )
        )


class RunReceipt(FrozenModel):
    elapsed_seconds: float = Field(default=0, ge=0)
    checkpoint_directory: str | None = None
    timings: tuple[dict[str, JsonValue], ...] = ()
    schema_version: Literal["experimental.receipt.v1"] = "experimental.receipt.v1"
    bundle_digest: str
    image_id: str
    framework_digest: str
    limits: WorkerLimits = Field(default_factory=WorkerLimits)
    operation: Literal["validate", "run"]
    actor_api_attempts: int = Field(default=0, ge=0)
    replayed_actor_requests: int = Field(default=0, ge=0)
    response: WorkerResponse


class ReportResponse(FrozenModel):
    bundle_digest: str
    notebook_json: str | None = None
    verification_findings: tuple[VerificationFinding, ...] = ()
    error: str | None = None
    checks: tuple[CheckResult, ...] = ()

    @property
    def passed(self) -> bool:
        return (
            self.error is None
            and self.notebook_json is not None
            and all(check.passed for check in self.checks)
            and all(
                not finding.required or finding.status == "verified"
                for finding in self.verification_findings
            )
        )


class ReportReceipt(FrozenModel):
    operation: Literal["preview", "report"]
    bundle_digest: str
    image_id: str
    framework_digest: str
    input_sha256: str
    actor_api_calls: Literal[0] = 0
    simulation_rerun: Literal[False] = False
    response: ReportResponse
