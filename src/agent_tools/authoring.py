"""Bounded coding-model calls with explicit, auditable context and no filesystem tools."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import cast

from pydantic import Field

from simulation_core.execution import JobManifest
from simulation_core.model_gateway import BoundedGateway, ModelGateway, ModelRequest
from simulation_core.request import ExperimentRequest
from simulation_core.types import FrozenModel, SimulationConfig

from .inventory import inventory
from .specs import BundleManifest

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
        "runtime",
        "benchmark",
        "execution",
        "registry",
        "observation",
        "logging",
        "validation",
        "provenance",
        "model_gateway",
    )
) + (
    "src/agent_tools/specs.py",
    "src/components/library.py",
    "src/components/policies/scripted.py",
    "src/components/protocols/simultaneous.py",
    "src/components/mechanisms/recording.py",
    "src/components/common/math/scalar.py",
    "src/components/solvers/response.py",
)


class SourceFile(FrozenModel):
    path: str
    content: str = Field(max_length=250000)


class CodingPlan(FrozenModel):
    summary: str = Field(min_length=1, max_length=3000)
    bundle_json: str = Field(min_length=1, max_length=150000)
    simulation_json: str = Field(min_length=1, max_length=100000)
    tests: tuple[SourceFile, ...] = Field(min_length=1, max_length=30)


class Implementation(FrozenModel):
    summary: str = Field(min_length=1, max_length=3000)
    files: tuple[SourceFile, ...] = Field(min_length=1, max_length=40)


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
        self, project: Path, gateway: ModelGateway, model: str, audit: Path, *, resume: bool = False
    ) -> None:
        self.project = project.resolve()
        self.gateway = BoundedGateway(
            gateway,
            max_calls=5,
            max_output_tokens_per_call=18000,
            max_request_chars=1_500_000,
            max_response_chars=600_000,
        )
        self.model = model
        self.audit = audit
        self.context = build_context(self.project)
        self.instructions = (self.project / "prompts/blind_coding_agent.md").read_text()
        sources = cast(list[dict[str, str]], self.context["sources"])
        manifest = {
            "source_files": [
                {"path": source["path"], "sha256": source["sha256"]} for source in sources
            ],
            "instructions_sha256": hashlib.sha256(self.instructions.encode()).hexdigest(),
            "access": "Explicit API payload only; no filesystem, shell, web, retrieval, or code-execution tools supplied",
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
            if self.gateway.calls >= self.gateway.max_calls:
                raise ValueError("Authoring API budget is exhausted")
        else:
            private_json(audit / "context_manifest.json", manifest)

    def call(
        self, task: dict[str, object], output: type[CodingPlan] | type[Implementation]
    ) -> CodingPlan | Implementation:
        if self.gateway.calls >= self.gateway.max_calls:
            raise ValueError("Authoring API budget is exhausted")
        index = self.gateway.calls + 1
        request = ModelRequest(
            actor_id="coding_agent",
            model=self.model,
            reasoning_effort="minimal" if self.model.startswith("muse-") else None,
            instructions=self.instructions,
            input_json=json.dumps({**task, "toolkit": self.context}),
            response_schema=output.model_json_schema(),
            max_output_tokens=18000,
        )
        private_json(self.audit / f"request-{index}.json", request.model_dump(mode="json"))
        response = self.gateway.complete(request)
        private_json(self.audit / f"response-{index}.json", response.model_dump(mode="json"))
        return output.model_validate_json(response.text)

    def plan(self, request: ExperimentRequest, experiment_id: str) -> CodingPlan:
        result = self.call(
            {
                "stage": "plan_and_tests",
                "request": request.model_dump(mode="json"),
                "experiment_id": experiment_id,
            },
            CodingPlan,
        )
        if not isinstance(result, CodingPlan):
            raise TypeError("Expected a coding plan")
        manifest = BundleManifest.model_validate_json(result.bundle_json)
        if manifest.experiment_id != experiment_id or manifest.version != "v1":
            raise ValueError("Plan namespace/version mismatch")
        JobManifest(
            request=request, simulation=SimulationConfig.model_validate_json(result.simulation_json)
        )
        if any(not safe_source_path(source.path, tests=True) for source in result.tests):
            raise ValueError("Planning stage may write only acceptance tests")
        return result

    def implement(
        self,
        request: ExperimentRequest,
        plan: CodingPlan,
        *,
        previous: Implementation | None = None,
        feedback: str | None = None,
    ) -> Implementation:
        task: dict[str, object] = {
            "stage": "implementation" if previous is None else "repair_implementation",
            "request": request.model_dump(mode="json"),
            "frozen_plan": plan.model_dump(mode="json"),
        }
        if previous is not None:
            task["previous_implementation"] = previous.model_dump(mode="json")
            task["validation_feedback"] = feedback
        result = self.call(task, Implementation)
        if not isinstance(result, Implementation):
            raise TypeError("Expected implementation files")
        if any(not safe_source_path(source.path, tests=False) for source in result.files):
            raise ValueError("Implementation may write only its package and README")
        return result


def materialize(
    root: Path,
    request: ExperimentRequest,
    plan: CodingPlan,
    implementation: Implementation,
    version: int,
) -> JobManifest:
    manifest = BundleManifest.model_validate_json(plan.bundle_json)
    manifest = manifest.model_copy(
        update={
            "version": f"v{version}",
            "repair_counts": {} if version == 1 else {"implementation_validation": version - 1},
        }
    )
    job = JobManifest(
        request=request, simulation=SimulationConfig.model_validate_json(plan.simulation_json)
    )
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
