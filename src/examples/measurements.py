"""A second declarative fixture demonstrating non-game transitions."""

from importlib.resources import files

from components.library import standard_registry
from simulation_core.execution import JobResult, JobRunner, LocalBackend
from simulation_core.request import ExperimentRequest
from simulation_core.types import RunResult, SimulationConfig


def run_job() -> JobResult:
    config = SimulationConfig.model_validate_json(
        files("examples").joinpath("configs/measurements.json").read_text()
    )
    request = ExperimentRequest.model_validate_json(
        files("examples").joinpath("configs/measurements_request.json").read_text()
    )
    return JobRunner(LocalBackend(standard_registry())).run(request, config)


def run_experiment() -> RunResult:
    return run_job().result


if __name__ == "__main__":
    print(run_job().model_dump_json(indent=2))
