"""Offline composition checks; the primary run exercises live integration once."""

from pathlib import Path

from agent_tools.fixtures import fixture_job
from extension_worker.runtime import load_registry
from extension_worker.verification import benchmark_preflight
from simulation_core.execution import JobManifest
from simulation_core.observation import observe, permissions_for


def test_extension_integrates_with_the_existing_runtime():
    _, registry = load_registry(Path("/bundle"))
    manifest = JobManifest.model_validate_json(Path("/job/manifest.json").read_text())
    config, state = fixture_job(manifest, registry)
    benchmark_preflight(config, registry, state)
    for actor in config.world.actors:
        observation = observe(actor, state, permissions_for(config, actor.id, state.phase))
        assert observation.actor_id == actor.id
