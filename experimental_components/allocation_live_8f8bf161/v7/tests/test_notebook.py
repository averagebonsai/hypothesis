from pathlib import Path

from experiment_extension.notebook import generate

from simulation_core.execution import JobResult
from simulation_core.request import ExperimentRequest
from simulation_core.types import RunResult, SimulationConfig, WorldState


def test_notebook_writes(tmp_path):
    sim = SimulationConfig.model_validate({"schema_version": "simulation.config.v1", "world": {"actors": [{"id": "allocator", "kind": "allocator", "action_space": {"schemas": {"allocate": "experimental.allocation_live_8f8bf161.action"}}, "policy_id": "scripted.v1", "policy_parameters": {"kind": "allocate", "payload": {"allocation": [5.0, 5.0]}}}], "parameters": {"budget": 10.0, "target": [8.0, 6.0]}}, "mechanism_id": "experimental.allocation_live_8f8bf161.mechanism", "protocol_id": "simultaneous.v1", "protocol_parameters": {"rounds": 1}})
    req = ExperimentRequest.model_validate({"schema_version": "experiment.request.v1", "hypothesis": "h"})
    state = WorldState.model_validate({"tick": 1, "phase": "finished", "public": {}, "private": {}})
    run = RunResult.model_validate({"status": "completed", "final_state": state.model_dump(mode="json"), "outcomes": [], "events": [], "assumptions": [], "component_ids": []})
    artifact = JobResult.model_validate({"schema_version": "simulation.job_result.v1", "manifest": {"schema_version": "simulation.job.v1", "request": req.model_dump(mode="json"), "simulation": sim.model_dump(mode="json")}, "result": run.model_dump(mode="json"), "benchmark": None})
    out = generate(artifact, Path(tmp_path))
    assert out.name == "results.ipynb" and out.exists()
