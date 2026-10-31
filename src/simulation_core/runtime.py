from copy import deepcopy

from .logging import log_committed_decisions
from .observation import observe
from .registry import ComponentRegistry
from .types import (
    Decision,
    Event,
    ModelCallRecord,
    ObservationPermissions,
    PrivateState,
    RunResult,
    SimulationConfig,
    TransitionResult,
    WorldState,
)
from .validation import validate_state


class SimulationRuntime:
    """Experiment-independent trusted loop; components are fresh for each run."""

    def __init__(self, registry: ComponentRegistry) -> None:
        self.registry = registry

    def run(self, config: SimulationConfig) -> RunResult:
        config = SimulationConfig.model_validate(config.model_dump())
        self.registry.validate_ids(config)
        world = config.world
        mechanism = self.registry.mechanisms[config.mechanism_id]()
        protocol = self.registry.protocols[config.protocol_id](deepcopy(config.protocol_parameters))
        actors = {actor.id: actor for actor in world.actors}
        policies = {
            aid: self.registry.policies[actor.policy_id](deepcopy(actor.policy_parameters))
            for aid, actor in actors.items()
        }
        for aid, policy in policies.items():
            policy.configure_action_schemas(
                {
                    kind: self.registry.action_schemas[schema_id]
                    for kind, schema_id in actors[aid].action_space.schemas.items()
                }
            )
        mechanism.validate_config(world.model_copy(deep=True))
        state = WorldState(
            tick=0,
            phase=protocol.initial_phase(),
            public=world.initial_public_state,
            private={aid: world.initial_private_state.get(aid, PrivateState()) for aid in actors},
        ).model_copy(deep=True)
        state = validate_state(state, set(actors))
        mechanism.validate_state(world.model_copy(deep=True), state.model_copy(deep=True))
        events = [Event(sequence=0, kind="initialized", state=state.model_copy(deep=True))]
        outcomes = []

        def terminal() -> bool:
            return protocol.is_terminal(world.model_copy(deep=True), state.model_copy(deep=True))

        while not terminal() and state.tick < config.max_steps:
            active = protocol.active_actor_ids(
                world.model_copy(deep=True), state.model_copy(deep=True)
            )
            if not active or len(set(active)) != len(active) or set(active) - actors.keys():
                raise ValueError("Invalid active actor set")
            decisions = []
            model_calls: list[ModelCallRecord] = []
            for aid in active:
                actor = actors[aid]
                permissions = config.permissions.get(aid, ObservationPermissions())
                observation = observe(actor, state, permissions)
                policy = policies[aid]
                if policy.required_observation_fields() - observation.visible.keys():
                    raise ValueError("Required observation fields unavailable")
                call_count = len(policy.model_calls())
                decision = policy.choose_action(observation)
                model_calls.extend(policy.model_calls()[call_count:])
                decision = Decision.model_validate(decision.model_dump()).model_copy(deep=True)
                action = decision.action
                if action.actor_id != aid or action.kind not in actor.action_space.schemas:
                    raise ValueError("Invalid action ownership or kind")
                schema = self.registry.action_schemas[actor.action_space.schemas[action.kind]]
                schema.model_validate(action.payload, strict=True)
                if set(decision.private_updates) - set(permissions.writable_private_fields):
                    raise ValueError("Unauthorized private update")
                if decision.memory_update is not None and not permissions.writable_memory:
                    raise ValueError("Unauthorized memory update")
                decisions.append(decision)
            actions = tuple(decision.action for decision in decisions)
            # Completeness is enforced independently of protocol-specific legality checks.
            if len(actions) != len(active) or {a.actor_id for a in actions} != set(active):
                raise ValueError("Exactly one action required per active actor")
            protocol.validate_action_batch(
                world.model_copy(deep=True),
                state.model_copy(deep=True),
                tuple(action.model_copy(deep=True) for action in actions),
            )
            mechanism.validate_actions(
                world.model_copy(deep=True),
                state.model_copy(deep=True),
                tuple(action.model_copy(deep=True) for action in actions),
            )
            transition = mechanism.transition(
                world.model_copy(deep=True),
                state.model_copy(deep=True),
                tuple(action.model_copy(deep=True) for action in actions),
            )
            transition = TransitionResult.model_validate(transition.model_dump())
            if set(transition.outcome.payoffs) - set(actors):
                raise ValueError("Unknown actor in outcome")
            if set(transition.private_updates) - set(actors):
                raise ValueError("Unknown actor in mechanism private updates")
            private = {aid: item.model_copy(deep=True) for aid, item in state.private.items()}
            for aid, update in transition.private_updates.items():
                private[aid] = update.model_copy(deep=True)
            for decision in decisions:
                aid = decision.action.actor_id
                previous = private[aid]
                # Avoid silent last-writer-wins when a mechanism and policy both edit own state.
                if aid in transition.private_updates and (
                    decision.private_updates or decision.memory_update is not None
                ):
                    raise ValueError("Conflicting mechanism and policy private updates")
                private[aid] = PrivateState(
                    facts={**previous.facts, **decision.private_updates},
                    memory=(
                        previous.memory
                        if decision.memory_update is None
                        else decision.memory_update
                    ),
                )
            proposed = WorldState(
                tick=state.tick + 1,
                phase=protocol.next_phase(world.model_copy(deep=True), state.model_copy(deep=True)),
                public=transition.public,
                private=private,
            )
            proposed = validate_state(proposed, set(actors))
            mechanism.validate_state(world.model_copy(deep=True), proposed.model_copy(deep=True))
            event = Event(
                sequence=len(events),
                kind="committed",
                state=proposed,
                actions=actions,
                decisions=tuple(decisions),
                outcome=transition.outcome,
                model_calls=tuple(model_calls),
            ).model_copy(deep=True)
            state = proposed.model_copy(deep=True)
            events.append(event)
            log_committed_decisions(event)
            outcomes.append(transition.outcome.model_copy(deep=True))
        return RunResult(
            status="completed" if terminal() else "step_limit",
            final_state=state,
            outcomes=tuple(outcomes),
            events=tuple(events),
            assumptions=config.assumptions,
            model_calls=tuple(call for event in events for call in event.model_calls),
            component_ids=(
                config.mechanism_id,
                config.protocol_id,
                *(actor.policy_id for actor in world.actors),
            ),
        )
