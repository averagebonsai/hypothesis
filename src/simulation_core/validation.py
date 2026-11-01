from pydantic import BaseModel

from .protocol import ProtocolRules
from .types import PrivateState, SimulationConfig, WorldState


def validate_state(state: WorldState, actor_ids: set[str]) -> WorldState:
    # Revalidate even objects returned by trusted components through model_copy.
    validated = WorldState.model_validate(state.model_dump())
    if set(validated.private) != actor_ids:
        raise ValueError("Private state must contain exactly the configured actors")
    return validated


def initial_state(config: "SimulationConfig", protocol: "ProtocolRules") -> WorldState:
    """Fresh isolated initial snapshot shared by execution and preflight adapters."""
    return WorldState(
        tick=0,
        phase=protocol.initial_phase(),
        public=config.world.initial_public_state,
        private={
            actor.id: config.world.initial_private_state.get(actor.id, PrivateState())
            for actor in config.world.actors
        },
    ).model_copy(deep=True)


def equivalent_payload_schema(actual: type[BaseModel], expected: type[BaseModel]) -> bool:
    """Conservative structural check, ignoring the model's display title.

    Does not attempt arbitrary JSON Schema subsumption or infer domain semantics.
    """
    actual_schema = actual.model_json_schema()
    expected_schema = expected.model_json_schema()
    actual_schema.pop("title", None)
    expected_schema.pop("title", None)
    return actual_schema == expected_schema
