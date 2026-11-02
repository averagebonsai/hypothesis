"""Framework-maintained integration checks, outside the experimental bundle."""

from pathlib import Path

from extension_worker.runtime import load_registry
from simulation_core.execution import JobManifest, JobRunner, LocalBackend
from simulation_core.logging import replay


def test_extension_integrates_with_the_existing_runtime():
    _, registry = load_registry(Path("/bundle"))
    manifest = JobManifest.model_validate_json(Path("/job/manifest.json").read_text())
    artifact = JobRunner(LocalBackend(registry)).run(manifest.request, manifest.simulation)
    assert artifact.result.status in {"completed", "step_limit"}
    assert artifact.result.final_state.tick <= manifest.simulation.max_steps
    assert replay(artifact.result.events)[-1] == artifact.result.final_state
    actors = {actor.id for actor in manifest.simulation.world.actors}
    assert all(set(event.state.private) == actors for event in artifact.result.events)
    assert type(artifact).model_validate_json(artifact.model_dump_json()) == artifact
