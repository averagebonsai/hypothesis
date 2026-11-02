"""Framework-maintained integration checks, outside the experimental bundle."""

from pathlib import Path

from agent_tools.fixtures import fixture_job
from extension_worker.diagnostics import record
from extension_worker.reporting import execute_report
from extension_worker.runtime import load_registry
from extension_worker.verification import assess, benchmark_preflight
from simulation_core.execution import JobManifest, JobRunner, LocalBackend
from simulation_core.logging import replay


def test_extension_integrates_with_the_existing_runtime():
    bundle, registry = load_registry(Path("/bundle"))
    manifest = JobManifest.model_validate_json(Path("/job/manifest.json").read_text())
    config, state = fixture_job(manifest, registry)
    benchmark_preflight(config, registry, state)
    artifact = JobRunner(LocalBackend(registry)).run(manifest.request, manifest.simulation)
    record(artifact)
    assert artifact.result.status in {"completed", "step_limit"}
    assert artifact.result.final_state.tick <= manifest.simulation.max_steps
    assert replay(artifact.result.events)[-1] == artifact.result.final_state
    actors = {actor.id for actor in manifest.simulation.world.actors}
    assert all(set(event.state.private) == actors for event in artifact.result.events)
    assert type(artifact).model_validate_json(artifact.model_dump_json()) == artifact
    findings = assess(artifact, bundle, registry)
    record(artifact, findings)
    assert all(not finding.required or finding.status == "verified" for finding in findings), (
        findings
    )
    if bundle.notebook is not None:
        notebook = execute_report(artifact, bundle.notebook)
        record(artifact, findings, notebook)
