import json
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field

from pydantic import BaseModel, JsonValue

from .contracts import ApplicabilityReport
from .mechanism import Mechanism
from .observation import observe, permissions_for
from .policy import Policy
from .protocol import ProtocolRules
from .request import ExperimentRequest
from .solver import GameView, Solver
from .types import Actor, SimulationConfig, WorldState
from .validation import equivalent_payload_schema, initial_state


class ComponentCompatibilityError(ValueError):
    """Declared components cannot be safely composed; detected without actor calls."""


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
            "solver_contracts": {
                key: factory().contract.model_dump(mode="json")
                for key, factory in self.solvers.items()
            },
            "solver_requirements": {
                key: (
                    requirement.__name__
                    if (requirement := factory().required_game_type)
                    else "GameView"
                )
                for key, factory in self.solvers.items()
            },
            "parameter_schemas": {
                key: model.model_json_schema() for key, model in self.parameter_schemas.items()
            },
            "action_schemas": {
                key: model.model_json_schema() for key, model in self.action_schemas.items()
            },
        }

    def benchmark_applicability(self, config: SimulationConfig) -> ApplicabilityReport | None:
        """Assess the configured benchmark without executing actors or a solver search."""
        self.validate_config(config)
        if config.benchmark is None:
            return None
        spec = config.benchmark
        mechanism = self.mechanisms[config.mechanism_id]()
        protocol = self.protocols[config.protocol_id](deepcopy(config.protocol_parameters))
        view = self.game_views[spec.game_view_id](
            config.model_copy(deep=True), initial_state(config, protocol), mechanism
        )
        return self.solvers[spec.solver_id]().assess(view, dict(spec.parameters))

    def create_policy(self, actor: Actor) -> Policy:
        """Fresh policy with only that actor's declared schemas, without decisions."""
        policy = self.policies[actor.policy_id](deepcopy(actor.policy_parameters))
        policy.configure_action_schemas(
            {
                kind: self.action_schemas[schema_id]
                for kind, schema_id in actor.action_space.schemas.items()
            }
        )
        return policy

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
        mechanism = self.mechanisms[config.mechanism_id]()
        mechanism.validate_config(config.world.model_copy(deep=True))

        protocol = self.protocols[config.protocol_id](config.protocol_parameters)
        protocol.validate_config(config.world.model_copy(deep=True))
        if set(config.phase_permissions) - protocol.declared_phases():
            raise ValueError("Unknown phase in observation permissions")

        try:
            mechanism.validate_schedule(
                config.world.model_copy(deep=True),
                protocol.decision_schedule(config.world.model_copy(deep=True)),
            )
            required = mechanism.required_action_schemas(config.world.model_copy(deep=True))
            if set(required) - {actor.id for actor in config.world.actors}:
                raise ValueError("Payload contract references unknown actors")
            for actor in config.world.actors:
                if actor.id in required and set(actor.action_space.schemas) != set(
                    required[actor.id]
                ):
                    raise ValueError(
                        f"Actor {actor.id} action kinds do not match the mechanism payload contract"
                    )
                for kind, schema in required.get(actor.id, {}).items():
                    actual = self.action_schemas.get(actor.action_space.schemas.get(kind, ""))
                    if actual is None or not equivalent_payload_schema(actual, schema):
                        raise ValueError(
                            f"Actor {actor.id} action {kind} requires payload schema {schema.__name__}"
                        )
            state = initial_state(config, protocol)
            mechanism.validate_state(
                config.world.model_copy(deep=True), state.model_copy(deep=True)
            )
            policies = {actor.id: self.create_policy(actor) for actor in config.world.actors}
            schedule = protocol.decision_schedule(config.world.model_copy(deep=True))
            if schedule is not None:
                # Repeated rounds with the same phase need only one permission check.
                checked = set()
                for phase in schedule:
                    for aid in phase.actor_ids:
                        if aid not in policies:
                            raise ValueError(f"Unknown scheduled actor {aid}")
                        key = (phase.name, aid)
                        if key in checked:
                            continue
                        checked.add(key)
                        permissions = permissions_for(config, aid, phase.name)
                        if policies[aid].required_observation_fields() - set(
                            permissions.public_fields
                        ):
                            raise ValueError(
                                f"Required observation fields unavailable for actor {aid} in phase {phase.name}"
                            )
            for aid in protocol.active_actor_ids(
                config.world.model_copy(deep=True), state.model_copy(deep=True)
            ):
                actor = next(actor for actor in config.world.actors if actor.id == aid)
                observation = observe(actor, state, permissions_for(config, aid, state.phase))
                if policies[aid].required_observation_fields() - observation.visible.keys():
                    raise ValueError(
                        f"Required observation fields unavailable for actor {aid} initially"
                    )
            if config.benchmark is not None:
                spec = config.benchmark
                view = self.game_views[spec.game_view_id](
                    config.model_copy(deep=True), state.model_copy(deep=True), mechanism
                )
                self.solvers[spec.solver_id]().validate_game(view)
        except (TypeError, ValueError) as exc:
            raise ComponentCompatibilityError(
                f"Incompatible configuration for mechanism {config.mechanism_id}: {exc}"
            ) from exc
