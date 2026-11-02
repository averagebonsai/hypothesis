"""Trusted fixture construction through JSON-aware boundaries, without actor calls."""

from pydantic import JsonValue

from simulation_core.execution import JobManifest
from simulation_core.protocol import ProtocolRules
from simulation_core.registry import ComponentRegistry
from simulation_core.types import SimulationConfig, WorldState
from simulation_core.validation import initial_state


def fixture_config(value: SimulationConfig | dict[str, JsonValue]) -> SimulationConfig:
    if isinstance(value, SimulationConfig):
        return value.model_copy(deep=True)
    return SimulationConfig.from_json_values(value)


def fixture_state(config: SimulationConfig, protocol: ProtocolRules) -> WorldState:
    return initial_state(config, protocol)


def fixture_job(
    manifest: JobManifest, registry: ComponentRegistry
) -> tuple[SimulationConfig, WorldState]:
    config = manifest.simulation.model_copy(deep=True)
    registry.validate_config(config)
    protocol = registry.protocols[config.protocol_id](config.protocol_parameters)
    return config, fixture_state(config, protocol)
