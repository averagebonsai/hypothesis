"""Stable fixtures; actual job manifests are temporary and automatically removed."""

from importlib.resources import files

from components.library import standard_registry
from simulation_core.execution import JobResult, JobRunner, LocalBackend
from simulation_core.registry import ComponentRegistry
from simulation_core.request import ExperimentRequest
from simulation_core.types import RunResult, SimulationConfig


def build_experiment(
    rounds: int = 1, max_steps: int = 100
) -> tuple[SimulationConfig, ComponentRegistry]:
    text = files("examples").joinpath("configs/prisoners_dilemma.json").read_text()
    config = SimulationConfig.model_validate_json(text)
    config = SimulationConfig.model_validate(
        config.model_copy(
            update={"protocol_parameters": {"rounds": rounds}, "max_steps": max_steps}
        ).model_dump()
    )
    return config, standard_registry()


def run_job(rounds: int = 1, max_steps: int = 100) -> JobResult:
    request = ExperimentRequest.model_validate_json(
        files("examples").joinpath("configs/prisoners_dilemma_request.json").read_text()
    )
    config, registry = build_experiment(rounds, max_steps)
    return JobRunner(LocalBackend(registry)).run(request, config)


def run_experiment(rounds: int = 1, max_steps: int = 100) -> RunResult:
    return run_job(rounds, max_steps).result


if __name__ == "__main__":
    print(run_job().model_dump_json(indent=2))
