"""Independent permission enforcement. Scheduling components cannot supply observations."""

from .types import Actor, Observation, ObservationPermissions, PrivateState, WorldState


def observe(actor: Actor, state: WorldState, permissions: ObservationPermissions) -> Observation:
    own = state.private[actor.id]
    return Observation(
        actor_id=actor.id,
        phase=state.phase,
        visible={
            key: state.public[key] for key in permissions.public_fields if key in state.public
        },
        private=PrivateState(
            facts={key: own.facts[key] for key in permissions.private_fields if key in own.facts},
            memory=own.memory if permissions.readable_memory else {},
        ),
        allowed_action_kinds=tuple(actor.action_space.schemas),
        writable_private_fields=permissions.writable_private_fields,
        writable_memory=permissions.writable_memory,
    ).model_copy(deep=True)
