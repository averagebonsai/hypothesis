from .types import WorldState


def validate_state(state: WorldState, actor_ids: set[str]) -> WorldState:
    # Revalidate even objects returned by trusted components through model_copy.
    validated = WorldState.model_validate(state.model_dump())
    if set(validated.private) != actor_ids:
        raise ValueError("Private state must contain exactly the configured actors")
    return validated
