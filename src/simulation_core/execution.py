"""Temporary job transport and a local trusted backend; not a security sandbox."""

from abc import ABC, abstractmethod
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal, Self

from pydantic import model_validator

from .benchmark import BenchmarkReport, BenchmarkRunner
from .provenance import resolve_pointer, same_json
from .registry import ComponentRegistry
from .request import ExperimentRequest
from .runtime import SimulationRuntime
from .types import FrozenModel, RunResult, SimulationConfig


class JobManifest(FrozenModel):
    schema_version: Literal["simulation.job.v1"] = "simulation.job.v1"
    request: ExperimentRequest
    simulation: SimulationConfig

    @model_validator(mode="after")
    def preserve_supplied_inputs(self) -> Self:
        for item in self.request.supplied_inputs:
            if item.target_path is not None and not same_json(
                resolve_pointer(self.simulation.model_dump(mode="json"), item.target_path),
                item.value,
            ):
                raise ValueError(f"Resolved configuration overrides supplied input: {item.name}")
        return self


class JobResult(FrozenModel):
    schema_version: Literal["simulation.job_result.v1"] = "simulation.job_result.v1"
    # In-memory/exportable provenance, independent of the deleted temporary files.
    manifest: JobManifest
    result: RunResult
    benchmark: BenchmarkReport | None = None


class ExecutionBackend(ABC):
    @abstractmethod
    def validate(self, manifest: JobManifest) -> None: ...

    @abstractmethod
    def execute(self, manifest_path: Path) -> RunResult: ...

    def benchmark(self, manifest: JobManifest, result: RunResult) -> BenchmarkReport | None:
        if manifest.simulation.benchmark is not None:
            raise NotImplementedError("Backend does not support benchmarks")
        return None


class LocalBackend(ExecutionBackend):
    """Only explicitly trusted registered components may run here."""

    def __init__(self, registry: ComponentRegistry) -> None:
        self.registry = registry

    def validate(self, manifest: JobManifest) -> None:
        self.registry.validate_config(manifest.simulation)

    def execute(self, manifest_path: Path) -> RunResult:
        manifest = JobManifest.model_validate_json(manifest_path.read_text())
        self.validate(manifest)
        return SimulationRuntime(self.registry).run(manifest.simulation)

    def benchmark(self, manifest: JobManifest, result: RunResult) -> BenchmarkReport | None:
        if manifest.simulation.benchmark is None:
            return None
        return BenchmarkRunner(self.registry).run(manifest.simulation, result)


class JobRunner:
    def __init__(self, backend: ExecutionBackend, temporary_root: Path | None = None) -> None:
        self.backend = backend
        self.temporary_root = temporary_root

    def run(self, request: ExperimentRequest, simulation: SimulationConfig) -> JobResult:
        manifest = JobManifest.model_validate(
            JobManifest(request=request, simulation=simulation).model_dump()
        )
        self.backend.validate(manifest.model_copy(deep=True))
        with TemporaryDirectory(prefix="simulation-job-", dir=self.temporary_root) as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(manifest.model_dump_json(indent=2))
            result = self.backend.execute(path)
            benchmark = self.backend.benchmark(
                manifest.model_copy(deep=True), result.model_copy(deep=True)
            )
            # Validate before returning, with cleanup even if execution/result validation fails.
            artifact = JobResult.model_validate(
                JobResult(manifest=manifest, result=result, benchmark=benchmark).model_dump()
            ).model_copy(deep=True)
        return artifact
