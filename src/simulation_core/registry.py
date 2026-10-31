import json
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import BaseModel, JsonValue

from .mechanism import Mechanism
from .policy import Policy
from .protocol import ProtocolRules
from .request import ExperimentRequest
from .solver import GameView, Solver
from .types import SimulationConfig, WorldState

type Parameters = dict[str, JsonValue]


@dataclass
class ComponentRegistry:
    """Trusted versioned factories; each resolution makes a fresh component per run/actor."""

    policies: dict[str, Callable[[Parameters], Policy]] = field(default_factory=dict)
    mechanisms: dict[str, Callable[[], Mechanism]] = field(default_factory=dict)
    protocols: dict[str, Callable[[Parameters], ProtocolRules]] = field(default_factory=dict)
    solvers: dict[str, Callable[[], Solver]] = field(default_factory=dict)
    game_views: dict[str, Callable[[SimulationConfig, WorldState, Mechanism], GameView]] = field(
        default_factory=dict
    )
    action_schemas: dict[str, type[BaseModel]] = field(default_factory=dict)

    parameter_schemas: dict[str, type[BaseModel]] = field(default_factory=dict)

    def describe(self) -> dict[str, JsonValue]:
        """Serializable inventory for a simulation-creating agent; no arbitrary imports."""
        return {
            "request_schema": ExperimentRequest.model_json_schema(),
            "simulation_schema": SimulationConfig.model_json_schema(),
            "policies": list(self.policies),
            "mechanisms": list(self.mechanisms),
            "protocols": list(self.protocols),
            "solvers": list(self.solvers),
            "game_views": list(self.game_views),
            "parameter_schemas": {
                key: model.model_json_schema() for key, model in self.parameter_schemas.items()
            },
            "action_schemas": {
                key: model.model_json_schema() for key, model in self.action_schemas.items()
            },
        }

    def validate_ids(self, config: SimulationConfig) -> None:
        if config.mechanism_id not in self.mechanisms or config.protocol_id not in self.protocols:
            raise ValueError("Unknown mechanism or protocol")
        if config.benchmark is not None and (
            config.benchmark.solver_id not in self.solvers
            or config.benchmark.game_view_id not in self.game_views
        ):
            raise ValueError("Unknown benchmark solver or game view")
        for actor in config.world.actors:
            if actor.policy_id not in self.policies:
                raise ValueError("Unknown policy")
            if set(actor.action_space.schemas.values()) - self.action_schemas.keys():
                raise ValueError("Unknown action schema")

    def validate_config(self, config: SimulationConfig) -> None:
        config = SimulationConfig.model_validate(config.model_dump())
        self.validate_ids(config)
        selections = [
            (config.protocol_id, config.protocol_parameters),
            (config.mechanism_id, config.world.parameters),
            *((actor.policy_id, actor.policy_parameters) for actor in config.world.actors),
        ]
        if config.benchmark is not None:
            selections.append((config.benchmark.solver_id, config.benchmark.parameters))
        for component_id, parameters in selections:
            schema = self.parameter_schemas.get(component_id)
            if schema is not None:
                schema.model_validate_json(json.dumps(parameters, allow_nan=False))
        self.mechanisms[config.mechanism_id]().validate_config(config.world.model_copy(deep=True))
