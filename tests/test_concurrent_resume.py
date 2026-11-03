"""Offline concurrency, canonical-event resumption and private role contracts."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

import pytest

from agent_tools.decision_ledger import DecisionLedger
from agent_tools.execution_settings import ActorExecutionSettings
from components.library import standard_registry
from simulation_core.behavior import ActorBehaviorSpec
from simulation_core.checkpoint import RuntimeCheckpoint, RuntimeOptions
from simulation_core.execution import JobManifest
from simulation_core.logging import replay
from simulation_core.model_gateway import BoundedGateway, FakeGateway, GatewayError, ModelRequest
from simulation_core.request import ExperimentRequest
from simulation_core.runtime import SimulationRuntime
from simulation_core.types import (
    ActionSpace,
    Actor,
    ObservationPermissions,
    PrivateState,
    SimulationConfig,
    WorldConfig,
)


def configuration(behaviors=()):
    profiles = {item.actor_id: item.model_dump(mode="json") for item in behaviors}
    return SimulationConfig(
        mechanism_id="recording.v1",
        protocol_id="simultaneous.v1",
        protocol_parameters={"rounds": 2},
        world=WorldConfig(
            parameters={"records_field": "records", "count_metric": "count"},
            actors=tuple(
                Actor(
                    id=aid,
                    kind="participant",
                    policy_id="llm.v1",
                    action_space=ActionSpace(schemas={"submit": "number.v1"}),
                    policy_parameters={
                        "model": "fake",
                        "instructions": "Choose independently.",
                        "max_calls": 6,
                        "max_attempts": 1,
                        **({"behavior": profiles[aid]} if aid in profiles else {}),
                    },
                )
                for aid in ("a", "b", "c")
            ),
            initial_private_state={
                aid: PrivateState(facts={"secret": aid}) for aid in ("a", "b", "c")
            },
        ),
        permissions={
            aid: ObservationPermissions(private_fields=("secret",)) for aid in ("a", "b", "c")
        },
    )


def response(request):
    return json.dumps(
        {
            "action": {"actor_id": request.actor_id, "kind": "submit", "payload": {"value": 1.0}},
            "rationale": "An offline test decision.",
            "memory_update": [{"key": "owner", "value_json": json.dumps(request.actor_id)}],
            "private_updates": [],
        }
    )


def test_simultaneous_requests_overlap_keep_private_views_and_commit_in_actor_order():
    barrier = Barrier(3, timeout=5)
    views = []
    lock = Lock()

    def respond(request):
        obs = json.loads(request.input_json)["observation"]
        with lock:
            views.append(obs)
        barrier.wait()  # A serial implementation cannot pass this test.
        return response(request)

    timings = []
    result = SimulationRuntime(
        standard_registry(FakeGateway(respond)),
        RuntimeOptions(
            max_concurrency=3,
            on_timing=timings.append,
        ),
    ).run(configuration())
    assert result.status == "completed"
    assert len(views) == 6
    for view in views:
        assert view["private"]["facts"] == {"secret": view["actor_id"]}
        assert view["visible"] == {}
    assert all("tick" not in view for view in views)
    for event in result.events[1:]:
        assert [a.actor_id for a in event.actions] == ["a", "b", "c"]
    assert replay(result.events)[-1] == result.final_state
    assert len([t for t in timings if t["stage"] == "actor"]) == 6
    assert len([t for t in timings if t["stage"] == "round"]) == 2


def test_partial_round_resume_keeps_successes_and_canonical_commits(tmp_path):
    snapshots = []
    seen = []

    def first(request):
        tick = int(request.decision_id.split(":")[-2])
        seen.append((request.actor_id, tick))
        if request.actor_id == "c" and tick == 1:
            raise GatewayError("offline_interruption")
        return response(request)

    config = configuration()
    with pytest.raises(RuntimeError):
        SimulationRuntime(
            standard_registry(FakeGateway(first)),
            RuntimeOptions(
                max_concurrency=3,
                on_checkpoint=snapshots.append,
            ),
        ).run(config)
    checkpoint = RuntimeCheckpoint.model_validate_json(snapshots[-1].model_dump_json())
    assert checkpoint.events[-1].state.tick == 1
    assert set(checkpoint.pending) == {"a", "b"}
    retried = []

    def second(request):
        retried.append((request.actor_id, int(request.decision_id.split(":")[-2])))
        return response(request)

    result = SimulationRuntime(
        standard_registry(FakeGateway(second)),
        RuntimeOptions(
            max_concurrency=3,
            checkpoint=checkpoint,
        ),
    ).run(config)
    assert retried == [("c", 1)]
    assert result.events[:2] == checkpoint.events
    assert len(result.events) == 3 and result.status == "completed"
    assert len(result.model_calls) == 7  # six choices plus the recorded failed attempt
    assert replay(result.events)[-1] == result.final_state
    assert all(state.memory == {"owner": aid} for aid, state in result.final_state.private.items())
    changed = config.model_copy(update={"max_steps": 1})
    with pytest.raises(ValueError, match="configuration mismatch"):
        SimulationRuntime(
            standard_registry(FakeGateway(second)), RuntimeOptions(checkpoint=checkpoint)
        ).run(changed)


def test_committed_checkpoint_resume_never_calls_completed_rounds():
    snapshots = []
    config = configuration()
    original = SimulationRuntime(
        standard_registry(FakeGateway(response)),
        RuntimeOptions(
            on_checkpoint=snapshots.append,
        ),
    ).run(config)
    provider = FakeGateway(lambda request: pytest.fail("Completed trajectory was called again"))
    resumed = SimulationRuntime(
        standard_registry(provider), RuntimeOptions(checkpoint=snapshots[-1])
    ).run(config)
    assert resumed == original and provider.requests == []


def test_ledger_survives_new_gateway_and_does_not_collapse_distinct_ticks(tmp_path):
    provider = FakeGateway(response)
    ledger = DecisionLedger(provider, tmp_path)
    request = ModelRequest(
        actor_id="a",
        model="fake",
        instructions="rules",
        input_json="{}",
        decision_id="round-0-a",
        response_schema={},
    )
    first = ledger.complete(request)
    restarted = DecisionLedger(provider, tmp_path)
    assert restarted.complete(request) == first and restarted.last_replayed
    changed = request.model_copy(update={"decision_id": "round-1-a"})
    restarted.complete(changed)
    assert not restarted.last_replayed and len(provider.requests) == 2
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in tmp_path.glob("*.json"))


def test_concurrent_ledger_and_budget_do_not_duplicate_requests_or_overspend(tmp_path):
    provider = FakeGateway(response)
    ledger = DecisionLedger(provider, tmp_path)
    request = ModelRequest(
        actor_id="a", model="fake", instructions="rules", input_json="{}", response_schema={}
    )
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(ledger.complete, [request] * 8))
    assert len(provider.requests) == 1
    bounded = BoundedGateway(provider, max_calls=2)

    def attempt(_):
        try:
            bounded.complete(request)
            return True
        except GatewayError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt, range(8))) == 2
    assert bounded.calls == 2


def test_behavior_profiles_are_preserved_and_only_sent_to_their_actor():
    profiles = (
        ActorBehaviorSpec(
            actor_id="a", objective="Support group welfare", behavioral_instructions="PRIVATE_COOP"
        ),
        ActorBehaviorSpec(
            actor_id="c",
            objective="Maximize own wealth",
            behavioral_instructions="PRIVATE_OPPORTUNIST",
        ),
    )
    config = configuration(profiles)
    request = ExperimentRequest(hypothesis="Private roles", actor_behaviors=profiles)
    JobManifest(request=request, simulation=config)
    provider = FakeGateway(response)
    SimulationRuntime(standard_registry(provider)).run(config)
    for call in provider.requests:
        assert ("PRIVATE_COOP" in call.instructions) == (call.actor_id == "a")
        assert ("PRIVATE_OPPORTUNIST" in call.instructions) == (call.actor_id == "c")
    resolved = ActorExecutionSettings(model="fake").resolve(config)
    assert resolved.world.actors[0].policy_parameters["behavior"] == profiles[0].model_dump(
        mode="json"
    )
    with pytest.raises(ValueError, match="overrides actor behavior"):
        JobManifest(request=request, simulation=configuration())
    with pytest.raises(ValueError, match="Duplicate"):
        JobManifest(
            request=request.model_copy(update={"actor_behaviors": (profiles[0], profiles[0])}),
            simulation=config,
        )


def test_checkpoint_deltas_never_rewrite_committed_events():
    from simulation_core.checkpoint import merge_checkpoint

    snapshots = []
    SimulationRuntime(
        standard_registry(FakeGateway(response)),
        RuntimeOptions(
            on_checkpoint=snapshots.append,
        ),
    ).run(configuration())
    initial = snapshots[0].model_dump(mode="json")
    merged = merge_checkpoint(None, {**initial, "event_count": 1})
    final = snapshots[-1].model_dump(mode="json")
    merged = merge_checkpoint(
        merged.model_dump(mode="json"),
        {
            **final,
            "events": final["events"][1:],
            "event_count": 3,
        },
    )
    assert merged == snapshots[-1]
    rewritten = json.loads(json.dumps(final))
    rewritten["events"][1]["state"]["public"]["tampered"] = True
    with pytest.raises(ValueError, match="rewrites"):
        merge_checkpoint(merged.model_dump(mode="json"), {**rewritten, "event_count": 3})
    with pytest.raises(ValueError, match="count mismatch"):
        merge_checkpoint(initial, {**final, "events": [], "event_count": 3})


def test_failed_provider_calls_consume_durable_budget_across_resume(tmp_path):
    def fail(request):
        raise GatewayError("offline_timeout")

    request = ModelRequest(
        actor_id="a", model="fake", instructions="rules", input_json="{}", response_schema={}
    )
    with pytest.raises(GatewayError, match="offline_timeout"):
        DecisionLedger(FakeGateway(fail), tmp_path, max_calls=1).complete(request)
    with pytest.raises(GatewayError, match="durable_call_budget_exhausted"):
        DecisionLedger(FakeGateway(response), tmp_path, max_calls=1).complete(request)


def test_prepared_request_variants_and_budget_are_valid():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "experiment_requests"
    settings = ActorExecutionSettings.model_validate_json(
        (root / "public_goods_fast.execution.json").read_text()
    )
    for name in ("public_goods_fast.json", "public_goods_fast_heterogeneous.json"):
        request = ExperimentRequest.model_validate_json((root / name).read_text())
        assert len(request.actor_behaviors) == 3
        values = {item.name: item.value for item in request.supplied_inputs}
        assert values["participant count"] == 3 and values["total rounds"] == 6
        assert values["last endowed round"] == 3
    config = configuration().model_copy(update={"protocol_parameters": {"rounds": 6}})
    settings.validate_budget(config)
    with pytest.raises(ValueError, match="36 calls"):
        settings.model_copy(update={"max_total_calls": 35}).validate_budget(config)


def test_uncertain_provider_outcome_is_not_silently_queried_again(tmp_path):
    request = ModelRequest(
        actor_id="a", model="fake", instructions="rules", input_json="{}", response_schema={}
    )

    def interrupted(request):
        raise OSError("Simulated process/storage failure")

    with pytest.raises(OSError):
        DecisionLedger(FakeGateway(interrupted), tmp_path).complete(request)
    provider = FakeGateway(lambda request: pytest.fail("An uncertain call was duplicated"))
    with pytest.raises(GatewayError, match="outcome_unresolved"):
        DecisionLedger(provider, tmp_path).complete(request)
    assert provider.requests == []
