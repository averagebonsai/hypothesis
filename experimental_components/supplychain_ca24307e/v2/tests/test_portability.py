"""Portable fixtures: tests never require CWD draft.json.

The deployed worker exposes /job/manifest.json or the bundle-relative
job.example.json (both JobManifest documents); draft.json is a CodingPlan
fallback for the authoring container only. These tests mimic a deployed
working directory without draft.json.
"""

import json
import shutil
from pathlib import Path

import helpers
from experiment_extension.mechanism import SupplyChainMechanism
from experiment_extension.schemas import SupplyChainParameters
from helpers import candidate_data, candidate_paths, step_day
from helpers import mechanism_and_state as _base_setup

from simulation_core.execution import JobManifest
from simulation_core.types import SimulationConfig, WorldState

ORDER = {"order_a": 80, "order_b": 80, "priority_a": 0, "priority_b": 0}
SUPPLY = {"produce": 80, "fulfill": 80, "ship_request": 80, "priority": 0}
ALLOCATE = {"allocate_a": 80, "allocate_b": 80}
PRODUCE = {"produce": 80}


def mechanism_and_state() -> tuple[SupplyChainMechanism, SimulationConfig, WorldState]:
    """Local setup: helper fixture plus draft-config validation through a fresh mechanism."""
    mechanism, config, state = _base_setup()
    assert SupplyChainMechanism().validate_config(config.world) is None
    return mechanism, config, state


def test_loader_ignores_working_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert not (tmp_path / "draft.json").exists()
    assert not (tmp_path / "job.example.json").exists()
    assert Path("/job/manifest.json") in candidate_paths()
    data = candidate_data()
    assert isinstance(data["simulation"], dict)
    mechanism, config, state = mechanism_and_state()
    assert isinstance(mechanism, SupplyChainMechanism)
    mechanism.validate_config(config.world)
    mechanism.validate_state(config.world, state)
    state = step_day(mechanism, config, state, ORDER, SUPPLY, SUPPLY, ALLOCATE, PRODUCE)
    assert state.public["day"] == 2


def test_deployed_manifest_directory_without_draft(tmp_path, monkeypatch) -> None:
    root = Path(helpers.__file__).resolve().parent.parent
    shutil.copy(root / "job.example.json", tmp_path / "job.example.json")
    monkeypatch.chdir(tmp_path)
    assert not (tmp_path / "draft.json").exists()
    manifest = JobManifest.from_json_values(json.loads((tmp_path / "job.example.json").read_text()))
    assert manifest.simulation.max_steps == 36
    data = candidate_data()
    assert data["simulation"]["max_steps"] == 36
    params = SupplyChainParameters.from_json_values(data["simulation"]["world"]["parameters"])
    assert params.horizon_days == 9
    _, config, _ = mechanism_and_state()
    assert config.max_steps == 36
