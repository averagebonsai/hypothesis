"""Host-side job composition shared by examples and trusted callers."""

from components.library import standard_registry
from simulation_core.execution import JobResult, JobRunner, LocalBackend
from simulation_core.model_gateway import BoundedGateway, ModelGateway
from simulation_core.request import ExperimentRequest
from simulation_core.types import SimulationConfig


def run_model_job(
    request: ExperimentRequest,
    config: SimulationConfig,
    gateway: ModelGateway,
    *,
    max_calls: int,
    max_output_tokens_per_call: int,
) -> JobResult:
    bounded = BoundedGateway(
        gateway, max_calls=max_calls, max_output_tokens_per_call=max_output_tokens_per_call
    )
    return JobRunner(LocalBackend(standard_registry(bounded))).run(request, config)
