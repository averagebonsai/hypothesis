"""Analytical, independent-grid, integration, and worker-boundary acceptance checks."""

import os
import socket
from pathlib import Path

import pytest
from experiment_extension.allocation import AllocationParameters, project_simplex

from extension_worker.runtime import load_registry
from simulation_core.execution import JobManifest, JobRunner, LocalBackend


def test_known_projection():
    assert project_simplex((8.0, 6.0), 10.0) == (6.0, 4.0)
    assert project_simplex((8.0, -2.0), 3.0) == (3.0, 0.0)
    assert project_simplex((-3.0, -3.0), 2.0) == (1.0, 1.0)


def test_invalid_projection_inputs():
    with pytest.raises(ValueError):
        AllocationParameters(budget=-1.0, target=(8.0, 6.0))
    with pytest.raises(ValueError):
        AllocationParameters(budget=10.0, target=(float("nan"), 6.0))


def test_optimum_dominates_independent_feasible_grid():
    # Independent two-dimensional reduction x2=10-x1 gives score
    # -(x1-8)^2-(4-x1)^2, maximized at x1=6.
    optimum = -8.0
    for index in range(1001):
        first = index / 100
        assert -((first - 8) ** 2) - (10 - first - 6) ** 2 <= optimum + 1e-10


def test_primary_action_is_preserved_against_separate_optimum():
    _, registry = load_registry(Path("/bundle"))
    job = JobManifest.model_validate_json(Path("/job/manifest.json").read_text())
    result = JobRunner(LocalBackend(registry)).run(job.request, job.simulation)
    assert result.result.events[-1].actions[0].payload["allocation"] == [5.0, 5.0]
    assert result.result.outcomes[-1].payoffs == {"allocator": -10.0}
    assert result.benchmark.result.equilibria[0].actions[0].payload["allocation"] == [6.0, 4.0]
    assert result.benchmark.result.equilibria[0].outcome.payoffs == {"allocator": -8.0}
    assert result.benchmark.observed_regrets == {"allocator": 2.0}


def test_worker_restrictions():
    assert os.geteuid() == 10001
    assert not Path("/var/run/docker.sock").exists()
    assert not Path("/opt/toolkit/.env").exists()
    for path in ("/bundle/unexpected", "/opt/toolkit/src/unexpected"):
        with pytest.raises(OSError):
            Path(path).write_text("must not write")
    with socket.socket() as connection:
        connection.settimeout(1)
        with pytest.raises(OSError):
            connection.connect(("8.8.8.8", 53))
    assert int(Path("/sys/fs/cgroup/pids.max").read_text()) <= 128
