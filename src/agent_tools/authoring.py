"""Auditable coding-model calls with explicit context and no filesystem tools."""

import hashlib
import json
import os
import time
from pathlib import Path, PurePosixPath
from typing import cast

from simulation_core.execution import JobManifest
from simulation_core.model_gateway import BoundedGateway, ModelGateway, ModelRequest
from simulation_core.request import ExperimentRequest
from simulation_core.types import FrozenModel

from .contracts import (
    AuthoredCandidate,
    CandidateResponse,
    CodingPlan,
    Implementation,
    ImplementationResponse,
    NotebookReview,
    PlanningResponse,
    ReviewRequest,
    SourceFile,
)
from .execution_settings import ActorExecutionSettings
from .guide import interface_guide
from .inventory import inventory
from .jobs import ToolJobManifest
from .planning import review_plan

SOURCE_FILES = tuple(
    "src/simulation_core/" + name + ".py"
    for name in (
        "types",
        "policy",
        "policy_metadata",
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
        "behavior",
        "checkpoint",
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
    "src/simulation_core/reports.py",
    "src/agent_tools/guide.py",
    "src/agent_tools/workspace.py",
    "src/agent_tools/starter.py",
    "src/agent_tools/execution_settings.py",
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


class CandidateValidationError(ValueError):
    def __init__(self, candidate: AuthoredCandidate, issues: tuple[str, ...]) -> None:
        self.candidate, self.issues = candidate, issues
        super().__init__("\n".join(issues))


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
    return {"sources": sources, "inventory": inventory(), "interface_guide": interface_guide()}


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
        max_output_tokens: int | None = None,
        instructions_path: Path | None = None,
        execution_settings: ActorExecutionSettings | None = None,
        content_review: bool = False,
        combined_authoring: bool = True,
        access_description: str = "Explicit API payload only; no filesystem, shell, web, retrieval, or code-execution tools supplied",
    ) -> None:
        self.reasoning_effort = reasoning_effort
        self.execution_settings = execution_settings
        self.content_review = content_review
        self.combined_authoring = combined_authoring
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
            "actor_execution": None
            if execution_settings is None
            else execution_settings.model_dump(mode="json"),
            "authoring_contract_version": 3,
            "combined_authoring": combined_authoring,
            "content_review": content_review,
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
        max_output_tokens: int | None = None,
        backend: str = "muse",
        sandbox: str | None = None,
        actor_max_output_tokens: int | None = None,
        actor_max_total_calls: int | None = None,
        actor_settings: ActorExecutionSettings | None = None,
        combined_authoring: bool = True,
        content_review: bool = False,
        reasoning_effort: str = "max",
    ) -> "CodingAgent":
        if backend == "muse":
            from components.gateways.settings import LiveModelSettings

            from .muse import MuseCodeGateway

            settings = LiveModelSettings.load(role="coding", env_file=project / ".env")
            actors = LiveModelSettings.load(role="actor", env_file=project / ".env")
            if actor_settings is not None and actor_settings.model != actors.model:
                raise ValueError("Actor settings must use the MODEL selected in the environment")
            return cls(
                project,
                MuseCodeGateway(
                    project, audit / "muse", settings.api_key, sandbox=sandbox, resume=resume
                ),
                settings.model,
                audit,
                resume=resume,
                max_calls=max_calls,
                max_output_tokens=max_output_tokens,
                combined_authoring=combined_authoring,
                execution_settings=actor_settings
                or ActorExecutionSettings(
                    model=actors.model,
                    max_output_tokens=actor_max_output_tokens,
                    max_total_calls=actor_max_total_calls,
                ),
                content_review=content_review,
                reasoning_effort=reasoning_effort,
                instructions_path=project / "prompts/muse_coding_agent.md",
                access_description="Muse Code filesystem and command tools in one persistent experiment-local session/container; trusted toolkit read-only; no host workspace or past experiments",
            )
        if backend != "api":
            raise ValueError("Coding backend must be muse or api")
        from components.gateways.live import configured_coding_gateway
        from components.gateways.settings import LiveModelSettings

        model, gateway = configured_coding_gateway(env_file=project / ".env")
        return cls(
            project,
            gateway,
            model,
            audit,
            resume=resume,
            max_calls=max_calls,
            max_output_tokens=max_output_tokens,
            combined_authoring=combined_authoring,
            content_review=content_review,
            reasoning_effort=reasoning_effort,
            execution_settings=actor_settings
            or ActorExecutionSettings(
                model=LiveModelSettings.load(role="actor", env_file=project / ".env").model,
                max_output_tokens=actor_max_output_tokens,
            ),
        )

    def call[T: FrozenModel](self, task: dict[str, object], output: type[T]) -> T:
        if self.gateway.max_calls is not None and self.gateway.calls >= self.gateway.max_calls:
            raise AuthoringBudgetError("Authoring API budget is exhausted")
        index = self.gateway.calls + 1
        effort = self.reasoning_effort
        if effort == "adaptive":
            stage = task.get("stage")
            repair_scope = task.get("repair_scope")
            if repair_scope == "report_only" or stage == "review_notebook":
                effort = "low"
            elif task.get("validation_feedback") or task.get("previous_candidate"):
                effort = "medium"
            else:
                effort = "high"
        request = ModelRequest(
            actor_id="coding_agent",
            model=self.model,
            reasoning_effort=effort,
            instructions=self.instructions,
            input_json=json.dumps(
                {
                    **task,
                    "toolkit": self.context,
                    **(
                        {"execution_capabilities": self.execution_settings.capabilities()}
                        if self.execution_settings
                        else {}
                    ),
                }
            ),
            response_schema=output.model_json_schema(),
            response_strict=False,
            max_output_tokens=self.max_output_tokens,
        )
        private_json(self.audit / f"request-{index}.json", request.model_dump(mode="json"))
        started = time.monotonic()
        succeeded = False
        try:
            response = self.gateway.complete(request)
            succeeded = True
        finally:
            private_json(
                self.audit / f"stage-timing-{index}.json",
                {
                    "stage": task.get("stage", "unknown"),
                    "elapsed_seconds": time.monotonic() - started,
                    "provider_completed": succeeded,
                },
            )
        private_json(self.audit / f"response-{index}.json", response.model_dump(mode="json"))
        return output.model_validate_json(response.text)

    def close(self) -> None:
        """Release an experiment's authoring resources after all stages are finished."""
        close = getattr(self.gateway.gateway, "close", None)
        if close is not None:
            close()

    def review_notebook(
        self,
        request: ExperimentRequest,
        plan: CodingPlan,
        implementation: Implementation,
        content: str,
        *,
        observed: bool,
    ) -> NotebookReview:
        notebook = json.loads(content)
        # Include text/metadata and figure descriptions, not redundant base64 images.
        for cell in notebook["cells"]:
            cell["outputs"] = [
                output
                for output in cell.get("outputs", [])
                if "image/png" not in output.get("data", {})
            ]
        return self.call(
            {
                "stage": "review_notebook",
                "request": request.model_dump(mode="json"),
                "frozen_plan": plan.model_dump(mode="json"),
                "previous_implementation": implementation.model_dump(mode="json"),
                "notebook": notebook,
                "observed": observed,
            },
            NotebookReview,
        )

    def author_candidate(
        self,
        request: ExperimentRequest,
        experiment_id: str,
        *,
        previous: AuthoredCandidate | None = None,
        feedback: str | None = None,
        repair_scope: str = "candidate",
    ) -> AuthoredCandidate:
        task: dict[str, object] = {
            "stage": "author_candidate",
            "request": request.model_dump(mode="json"),
            "experiment_id": experiment_id,
            "repair_scope": repair_scope,
        }
        if previous is not None:
            task["previous_candidate"] = previous.model_dump(mode="json")
        if feedback is not None:
            task["validation_feedback"] = feedback
        response = self.call(task, CandidateResponse)
        if response.review is not None:
            raise AuthoringReviewRequired(response.review)
        assert response.candidate is not None
        result = response.candidate
        plan = result.plan.model_copy(
            update={"tests": self._normalize(result.plan.tests, "candidate_tests")}
        )
        if self.execution_settings is not None and plan.simulation is not None:
            plan = plan.model_copy(
                update={"simulation": self.execution_settings.resolve(plan.simulation)}
            )
        implementation = result.implementation.model_copy(
            update={"files": self._normalize(result.implementation.files, "candidate_files")}
        )
        result = AuthoredCandidate(plan=plan, implementation=implementation)
        issues = list(review_plan(self.project, request, experiment_id, plan))
        paths = [file.path for file in implementation.files]
        if len(set(paths)) != len(paths) or "experiment_extension/__init__.py" not in paths:
            issues.append("Candidate needs unique source files and an explicit package initializer")
        if previous is not None and repair_scope == "report_only":
            notebook = previous.plan.bundle.notebook
            module = notebook.generator.split(":")[0].replace(".", "/") + ".py" if notebook else ""
            before = {file.path: file.content for file in previous.implementation.files}
            after = {file.path: file.content for file in implementation.files}
            if (
                plan != previous.plan
                or set(before) != set(after)
                or any(before[path] != after[path] for path in before if path != module)
            ):
                issues.append(
                    "Report-only repair changed configuration, tests or scientific source"
                )
        before_files = (
            {
                file.path: file.content
                for file in (*previous.plan.tests, *previous.implementation.files)
            }
            if previous
            else {}
        )
        after_files = {file.path: file.content for file in (*plan.tests, *implementation.files)}
        private_json(
            self.audit / f"candidate-review-{self.gateway.calls}.json",
            {
                "issues": issues,
                "repair_scope": repair_scope,
                "changed_files": sorted(
                    path
                    for path in before_files.keys() | after_files.keys()
                    if before_files.get(path) != after_files.get(path)
                ),
            },
        )
        if issues:
            raise CandidateValidationError(result, tuple(issues))
        return result

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
        if self.execution_settings is not None and result.simulation is not None:
            result = result.model_copy(
                update={"simulation": self.execution_settings.resolve(result.simulation)}
            )
            private_json(
                self.audit / f"execution-settings-{self.gateway.calls}.json",
                self.execution_settings.model_dump(mode="json"),
            )
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
