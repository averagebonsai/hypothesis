from pathlib import Path

import pytest
from pydantic import ValidationError

from examples.payoff_matrix import build_experiment, run_job
from simulation_core.execution import (
    ExecutionBackend,
    JobManifest,
    JobResult,
    JobRunner,
    LocalBackend,
)
from simulation_core.logging import replay
from simulation_core.provenance import resolve_pointer, same_json
from simulation_core.request import ExperimentRequest, SuppliedInput
from simulation_core.types import Assumption, SimulationConfig


def test_incomplete_request_is_valid_but_not_an_execution_spec():
    request = ExperimentRequest(hypothesis="How does entry affect prices?")
    assert request.supplied_inputs == ()
    assert ExperimentRequest.model_validate_json(request.model_dump_json()) == request
    with pytest.raises(ValidationError):
        SimulationConfig.model_validate_json(request.model_dump_json())
    with pytest.raises(ValidationError):
        ExperimentRequest(
            hypothesis="question", supplied_inputs=(SuppliedInput(name="cost", value=float("inf")),)
        )


def test_manifest_preserves_mapped_user_inputs():
    config, _ = build_experiment()
    request = ExperimentRequest(
        hypothesis="One round?",
        supplied_inputs=(
            SuppliedInput(name="round count", value=1, target_path="/protocol_parameters/rounds"),
        ),
    )
    manifest = JobManifest(request=request, simulation=config)
    assert JobManifest.model_validate_json(manifest.model_dump_json()) == manifest
    changed = config.model_copy(update={"protocol_parameters": {"rounds": 2}})
    with pytest.raises(ValidationError, match="overrides supplied input"):
        JobManifest(request=request, simulation=changed)


def test_assumptions_reference_actual_values():
    config, _ = build_experiment()
    assumption = Assumption(
        path="/max_steps",
        value=config.max_steps,
        source="model",
        rationale="Bound this synthetic run.",
    )
    valid = config.model_copy(update={"assumptions": (assumption,)})
    assert SimulationConfig.model_validate(valid.model_dump()).assumptions == (assumption,)
    with pytest.raises(ValidationError, match="differs"):
        SimulationConfig.model_validate(valid.model_copy(update={"max_steps": 5}).model_dump())
    with pytest.raises(ValidationError, match="Duplicate"):
        SimulationConfig.model_validate(
            config.model_copy(update={"assumptions": (assumption, assumption)}).model_dump()
        )
    with pytest.raises(ValidationError, match="Unresolved"):
        SimulationConfig.model_validate(
            config.model_copy(
                update={"assumptions": (assumption.model_copy(update={"path": "/world/missing"}),)}
            ).model_dump()
        )
    for path in ("max_steps", "/bad~escape", "/assumptions/0/value"):
        with pytest.raises(ValidationError):
            Assumption(path=path, value=1, source="default", rationale="Test")
    with pytest.raises(ValidationError):
        Assumption(path="/max_steps", value=1, source="unsupported", rationale="Test")


def test_json_pointer_escaping_and_boolean_preservation():
    assert resolve_pointer({"a/b": {"~field": [None, 3]}}, "/a~1b/~0field/1") == 3
    for path in ("/items/01", "/items/-", "/items/9"):
        with pytest.raises(ValueError):
            resolve_pointer({"items": [1]}, path)
    assert not same_json({"x": [True]}, {"x": [1]})


class WatchingBackend(LocalBackend):
    path: Path | None = None

    def execute(self, manifest_path):
        self.path = manifest_path
        assert manifest_path.is_file()
        manifest = JobManifest.model_validate_json(manifest_path.read_text())
        assert manifest.request.hypothesis
        return super().execute(manifest_path)


def test_temporary_job_cleanup_and_retained_provenance(tmp_path):
    config, registry = build_experiment()
    backend = WatchingBackend(registry)
    request = ExperimentRequest(hypothesis="Run the configured fixture.")
    artifact = JobRunner(backend, temporary_root=tmp_path).run(request, config)
    assert backend.path is not None and not backend.path.exists()
    assert not backend.path.parent.exists()
    assert list(tmp_path.iterdir()) == []
    assert artifact.manifest.simulation == config
    assert artifact.manifest.request == request
    assert artifact.result.outcomes[0].payoffs == {"A": 0.0, "B": 5.0}
    assert replay(artifact.result.events)[-1] == artifact.result.final_state
    assert JobResult.model_validate_json(artifact.model_dump_json()) == artifact


def test_temporary_job_cleanup_on_failure_and_no_cross_job_files(tmp_path):
    config, registry = build_experiment()

    class FailingBackend(WatchingBackend):
        def execute(self, manifest_path):
            self.path = manifest_path
            raise RuntimeError("execution failed")

    backend = FailingBackend(registry)
    request = ExperimentRequest(hypothesis="Failure cleanup check.")
    runner = JobRunner(backend, temporary_root=tmp_path)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="execution failed"):
            runner.run(request, config)
        assert backend.path is not None and not backend.path.exists()
        assert list(tmp_path.iterdir()) == []


def test_component_parameters_validated_before_execution(tmp_path):
    config, registry = build_experiment()
    backend = WatchingBackend(registry)
    config = config.model_copy(update={"protocol_parameters": {"rounds": "one"}})
    with pytest.raises(ValidationError):
        JobRunner(backend, temporary_root=tmp_path).run(
            ExperimentRequest(hypothesis="Invalid job"), config
        )
    assert backend.path is None
    assert list(tmp_path.iterdir()) == []


def test_example_uses_job_path_and_retains_structured_assumptions():
    artifact = run_job()
    assert artifact.result.assumptions == artifact.manifest.simulation.assumptions
    assert {a.source for a in artifact.result.assumptions} == {"user", "textbook", "default"}
    assert artifact.manifest.request.supplied_inputs
    assert issubclass(LocalBackend, ExecutionBackend)
