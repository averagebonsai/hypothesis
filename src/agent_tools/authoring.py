"""Auditable coding-model calls with explicit context and no filesystem tools."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import cast

from simulation_core.execution import JobManifest
from simulation_core.model_gateway import BoundedGateway, ModelGateway, ModelRequest
from simulation_core.request import ExperimentRequest
from simulation_core.types import FrozenModel

from .contracts import (
    CodingPlan,
    Implementation,
    ImplementationResponse,
    PlanningResponse,
    ReviewRequest,
    SourceFile,
)
from .inventory import inventory
from .jobs import ToolJobManifest
from .planning import review_plan

SOURCE_FILES = tuple(
    "src/simulation_core/" + name + ".py"
    for name in (
        "types",
        "policy",
        "mechanism",
        "protocol",
        "solver",
        "analysis",
        "contracts",
        "domains",
        "game_view",
        "request",
        "problems",
        "benchmark",
        "execution",
        "observation",
        "model_gateway",
    )
) + (
    "src/agent_tools/specs.py",
    "src/agent_tools/contracts.py",
    "src/agent_tools/jobs.py",
    "src/agent_tools/checks.py",
    "src/agent_tools/fixtures.py",
    "src/agent_tools/planning.py",
    "src/agent_tools/verification.py",
    "src/simulation_core/reporting.py",
    "src/components/library.py",
    "src/components/policies/scripted.py",
    "src/components/policies/llm.py",
    "src/components/protocols/simultaneous.py",
    "src/components/mechanisms/recording.py",
    "src/components/common/math/scalar.py",
    "src/components/solvers/response.py",
)


class AuthoringReviewRequired(RuntimeError):
    def __init__(self, review: ReviewRequest) -> None:
        self.review = review
        super().__init__(review.reason)


class AuthoringBudgetError(ValueError):
    pass


class PlanValidationError(ValueError):
    def __init__(self, plan: CodingPlan, issues: tuple[str, ...]) -> None:
        self.plan = plan
        self.issues = issues
        super().__init__("\n".join(issues))


def private_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def safe_source_path(path: str, *, tests: bool) -> bool:
    if not tests and path == "README.md":
        return True
    parsed = PurePosixPath(path)
    root = "tests" if tests else "experiment_extension"
    return (
        not parsed.is_absolute()
        and parsed.as_posix() == path
        and len(parsed.parts) > 1
        and parsed.parts[0] == root
        and parsed.suffix == ".py"
        and all(part.isidentifier() for part in parsed.parts[1:-1])
        and parsed.stem.isidentifier()
    )


def build_context(project: Path) -> dict[str, object]:
    sources = []
    for relative in SOURCE_FILES:
        path = project / relative
        if any(parent.is_symlink() for parent in (path, *path.parents) if parent != project.parent):
            raise ValueError("Authoring context cannot contain symbolic links")
        sources.append(
            {
                "path": relative,
                "content": path.read_text(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return {"sources": sources, "inventory": inventory()}


class CodingAgent:
    def __init__(
        self,
        project: Path,
        gateway: ModelGateway,
        model: str,
        audit: Path,
        *,
        resume: bool = False,
        max_calls: int | None = None,
        reasoning_effort: str = "max",
        max_output_tokens: int = 32000,
        instructions_path: Path | None = None,
        access_description: str = "Explicit API payload only; no filesystem, shell, web, retrieval, or code-execution tools supplied",
    ) -> None:
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens
        self.project = project.resolve()
        self.gateway = BoundedGateway(
            gateway,
            max_calls=max_calls,
            max_output_tokens_per_call=max_output_tokens,
            max_request_chars=1_500_000,
            max_response_chars=600_000,
        )
        self.model = model
        self.audit = audit
        self.context = build_context(self.project)
        self.instructions = (
            instructions_path or self.project / "prompts/blind_coding_agent.md"
        ).read_text()
        sources = cast(list[dict[str, str]], self.context["sources"])
        manifest = {
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "authoring_contract_version": 2,
            "source_files": [
                {"path": source["path"], "sha256": source["sha256"]} for source in sources
            ],
            "instructions_sha256": hashlib.sha256(self.instructions.encode()).hexdigest(),
            "access": access_description,
            "excluded": [
                "experimental_components/**",
                "tests/**",
                "docs/**",
                "visualisations/**",
                ".env",
                "Git history",
                "this conversation",
            ],
        }
        if resume:
            previous = json.loads((audit / "context_manifest.json").read_text())
            if previous != manifest:
                raise ValueError("Cannot resume with changed source context or instructions")
            requests = sorted(audit.glob("request-*.json"))
            for path in requests:
                saved = ModelRequest.model_validate_json(path.read_text())
                if (
                    json.loads(saved.input_json)["toolkit"] != self.context
                    or saved.instructions != self.instructions
                ):
                    raise ValueError("Resume payload differs from the audited context")
            self.gateway.calls = len(requests)
            if self.gateway.max_calls is not None and self.gateway.calls >= self.gateway.max_calls:
                raise AuthoringBudgetError("Authoring API budget is exhausted")
        else:
            private_json(audit / "context_manifest.json", manifest)

    @classmethod
    def from_environment(
        cls,
        project: Path,
        audit: Path,
        *,
        resume: bool = False,
        max_calls: int | None = None,
        max_output_tokens: int = 32000,
        backend: str = "muse",
        sandbox: str | None = None,
    ) -> "CodingAgent":
        if backend == "muse":
            from components.gateways.settings import LiveModelSettings

            from .muse import MuseCodeGateway

            settings = LiveModelSettings.load(role="coding", env_file=project / ".env")
            return cls(
                project,
                MuseCodeGateway(project, audit / "muse", settings.api_key, sandbox=sandbox),
                settings.model,
                audit,
                resume=resume,
                max_calls=max_calls,
                max_output_tokens=max_output_tokens,
                instructions_path=project / "prompts/muse_coding_agent.md",
                access_description="Muse Code filesystem and command tools inside a fresh Docker container; trusted toolkit read-only; no host workspace, history, or past experiments",
            )
        if backend != "api":
            raise ValueError("Coding backend must be muse or api")
        from components.gateways.live import configured_coding_gateway

        model, gateway = configured_coding_gateway(env_file=project / ".env")
        return cls(
            project,
            gateway,
            model,
            audit,
            resume=resume,
            max_calls=max_calls,
            max_output_tokens=max_output_tokens,
        )

    def call[T: FrozenModel](self, task: dict[str, object], output: type[T]) -> T:
        if self.gateway.max_calls is not None and self.gateway.calls >= self.gateway.max_calls:
            raise AuthoringBudgetError("Authoring API budget is exhausted")
        index = self.gateway.calls + 1
        request = ModelRequest(
            actor_id="coding_agent",
            model=self.model,
            reasoning_effort=self.reasoning_effort,
            instructions=self.instructions,
            input_json=json.dumps({**task, "toolkit": self.context}),
            response_schema=output.model_json_schema(),
            response_strict=False,
            max_output_tokens=self.max_output_tokens,
        )
        private_json(self.audit / f"request-{index}.json", request.model_dump(mode="json"))
        response = self.gateway.complete(request)
        private_json(self.audit / f"response-{index}.json", response.model_dump(mode="json"))
        return output.model_validate_json(response.text)

    def plan(
        self,
        request: ExperimentRequest,
        experiment_id: str,
        *,
        previous: CodingPlan | None = None,
        feedback: str | None = None,
    ) -> CodingPlan:
        task: dict[str, object] = {
            "stage": "plan_and_tests",
            "request": request.model_dump(mode="json"),
            "experiment_id": experiment_id,
        }
        if previous is not None:
            task["previous_plan"] = previous.model_dump(mode="json")
        if feedback is not None:
            task["validation_feedback"] = feedback
        response = self.call(task, PlanningResponse)
        if response.review is not None:
            raise AuthoringReviewRequired(response.review)
        result = response.plan
        if not isinstance(result, CodingPlan):
            raise TypeError("Expected a coding plan")
        result = result.model_copy(update={"tests": self._normalize(result.tests, "plan")})
        issues = review_plan(self.project, request, experiment_id, result)
        private_json(self.audit / f"plan-review-{self.gateway.calls}.json", {"issues": issues})
        if issues:
            raise PlanValidationError(result, issues)
        return result

    def implement(
        self,
        request: ExperimentRequest,
        plan: CodingPlan,
        *,
        previous: Implementation | None = None,
        feedback: str | None = None,
    ) -> Implementation:
        issues = review_plan(
            self.project,
            request,
            plan.bundle.experiment_id,
            plan,
        )
        if issues:
            raise PlanValidationError(plan, issues)
        task: dict[str, object] = {
            "stage": "implementation" if previous is None else "repair_implementation",
            "request": request.model_dump(mode="json"),
            "frozen_plan": plan.model_dump(mode="json"),
        }
        if previous is not None:
            task["previous_implementation"] = previous.model_dump(mode="json")
        if feedback is not None:
            task["validation_feedback"] = feedback
        response = self.call(task, ImplementationResponse)
        if response.review is not None:
            raise AuthoringReviewRequired(response.review)
        result = response.implementation
        if not isinstance(result, Implementation):
            raise TypeError("Expected implementation files")
        if any(not safe_source_path(source.path, tests=False) for source in result.files):
            raise ValueError("Implementation may write only its package and README")
        return result.model_copy(update={"files": self._normalize(result.files, "implementation")})

    def _normalize(self, sources: tuple[SourceFile, ...], stage: str) -> tuple[SourceFile, ...]:
        from .formatting import normalize_sources

        normalized, changes = normalize_sources(self.project, sources)
        private_json(self.audit / f"format-{stage}-{self.gateway.calls}.json", changes)
        return normalized


def materialize(
    root: Path,
    request: ExperimentRequest,
    plan: CodingPlan,
    implementation: Implementation,
    version: int,
) -> JobManifest | ToolJobManifest:
    manifest = plan.bundle
    manifest = manifest.model_copy(
        update={
            "version": f"v{version}",
            "repair_counts": {} if version == 1 else {"implementation_validation": version - 1},
        }
    )
    job: JobManifest | ToolJobManifest
    if plan.kind == "tool":
        assert plan.tool is not None
        job = ToolJobManifest(request=request, tool=plan.tool)
    else:
        assert plan.simulation is not None
        job = JobManifest(request=request, simulation=plan.simulation)
    if root.exists():
        raise ValueError("Never overwrite an existing experiment version")
    sources = (*plan.tests, *implementation.files)
    names = [source.path for source in sources]
    if len(names) != len(set(names)) or "experiment_extension/__init__.py" not in names:
        raise ValueError("Candidate needs unique files and an explicit package initializer")
    root.mkdir(parents=True)
    for source in sources:
        if not safe_source_path(source.path, tests=source in plan.tests):
            raise ValueError("Unsafe generated path")
        path = root / source.path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x") as stream:
            stream.write(source.content)
    (root / "bundle.json").write_text(manifest.model_dump_json(indent=2) + "\n")
    (root / "job.example.json").write_text(job.model_dump_json(indent=2) + "\n")
    return job
