import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy

from .checkpoint import RuntimeCheckpoint, RuntimeOptions, config_digest
from .logging import log_committed_decisions, replay
from .observation import observe, permissions_for
from .registry import ComponentRegistry
from .types import (
    Decision,
    Event,
    ModelCallRecord,
    Observation,
    PrivateState,
    RunResult,
    SimulationConfig,
    TransitionResult,
    WorldState,
)
from .validation import initial_state, validate_state


class SimulationRuntime:
    """Experiment-independent trusted loop; components are fresh for each run."""

    def __init__(self, registry: ComponentRegistry, options: RuntimeOptions | None = None) -> None:
        self.registry = registry
        self.options = options or RuntimeOptions()

    def run(self, config: SimulationConfig) -> RunResult:
        config = SimulationConfig.model_validate(config.model_dump())
        fingerprint = config_digest(config)
        self.registry.validate_config(config)
        world = config.world
        mechanism = self.registry.mechanisms[config.mechanism_id]()
        protocol = self.registry.protocols[config.protocol_id](deepcopy(config.protocol_parameters))
        actors = {actor.id: actor for actor in world.actors}
        policies = {aid: self.registry.create_policy(actor) for aid, actor in actors.items()}
        state = initial_state(config, protocol)
        state = validate_state(state, set(actors))
        mechanism.validate_state(world.model_copy(deep=True), state.model_copy(deep=True))
        events = [Event(sequence=0, kind="initialized", state=state.model_copy(deep=True))]
        outcomes = []
        pending: dict[str, Decision] = {}
        saved_calls: dict[str, tuple[ModelCallRecord, ...]] = {}
        checkpoint = self.options.checkpoint
        if checkpoint is not None:
            checkpoint.validate_config(config)
            snapshots = replay(checkpoint.events)
            if snapshots[0] != state:
                raise ValueError("Checkpoint initialization differs from configuration")
            for snapshot in snapshots:
                mechanism.validate_state(
                    world.model_copy(deep=True), snapshot.model_copy(deep=True)
                )
            events = list(checkpoint.events)
            state = snapshots[-1]
            outcomes = [event.outcome for event in events if event.outcome is not None]
            pending = dict(checkpoint.pending)
            saved_calls = dict(checkpoint.pending_calls)
            for aid, policy in policies.items():
                policy.restore_model_calls(
                    tuple(
                        call
                        for event in events
                        for call in event.model_calls
                        if call.actor_id == aid
                    )
                    + saved_calls.get(aid, ())
                )

        def persist() -> None:
            if self.options.on_checkpoint is not None:
                self.options.on_checkpoint(
                    RuntimeCheckpoint.create(config, tuple(events), pending, saved_calls)
                )

        persist()

        def terminal() -> bool:
            return protocol.is_terminal(world.model_copy(deep=True), state.model_copy(deep=True))

        while not terminal() and state.tick < config.max_steps:
            active = protocol.active_actor_ids(
                world.model_copy(deep=True), state.model_copy(deep=True)
            )
            if not active or len(set(active)) != len(active) or set(active) - actors.keys():
                raise ValueError("Invalid active actor set")
            round_started = time.monotonic()
            if set(pending) - set(active) or set(saved_calls) - set(active):
                raise ValueError("Checkpoint contains inactive actors")
            observations = {}
            for aid in active:
                actor = actors[aid]
                observation = observe(actor, state, permissions_for(config, aid, state.phase))
                if policies[aid].required_observation_fields() - observation.visible.keys():
                    raise ValueError("Required observation fields unavailable")
                observations[aid] = observation
                policies[aid].set_decision_context(f"{fingerprint}:{state.tick}:{aid}")
            baseline = {
                aid: len(policies[aid].model_calls()) - len(saved_calls.get(aid, ()))
                for aid in active
            }

            def choose(
                aid: str,
                observations: dict[str, Observation] = observations,
                tick: int = state.tick,
            ) -> Decision:
                started = time.monotonic()
                try:
                    return policies[aid].choose_action(observations[aid])
                finally:
                    if self.options.on_timing is not None:
                        self.options.on_timing(
                            {
                                "stage": "actor",
                                "tick": tick,
                                "actor_id": aid,
                                "seconds": time.monotonic() - started,
                            }
                        )

            failure: BaseException | None = None
            with ThreadPoolExecutor(max_workers=self.options.max_concurrency) as pool:
                futures = {pool.submit(choose, aid): aid for aid in active if aid not in pending}
                for future in as_completed(futures):
                    aid = futures[future]
                    try:
                        pending[aid] = future.result().model_copy(deep=True)
                    except Exception as exc:  # noqa: BLE001 - retain completed peers before stopping
                        failure = failure or exc
                    saved_calls[aid] = policies[aid].model_calls()[baseline[aid] :]
                    persist()
            if failure is not None:
                raise failure
            decisions = []
            model_calls: list[ModelCallRecord] = []
            for aid in active:
                actor = actors[aid]
                permissions = permissions_for(config, aid, state.phase)
                decision = pending[aid]
                model_calls.extend(saved_calls.get(aid, ()))
                decision = Decision.model_validate(decision.model_dump()).model_copy(deep=True)
                action = decision.action
                if action.actor_id != aid or action.kind not in actor.action_space.schemas:
                    raise ValueError("Invalid action ownership or kind")
                schema = self.registry.action_schemas[actor.action_space.schemas[action.kind]]
                schema.model_validate_json(json.dumps(action.payload, allow_nan=False), strict=True)
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
            pending = {}
            saved_calls = {}
            persist()
            if self.options.on_timing is not None:
                self.options.on_timing(
                    {
                        "stage": "round",
                        "tick": state.tick,
                        "seconds": time.monotonic() - round_started,
                    }
                )
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
