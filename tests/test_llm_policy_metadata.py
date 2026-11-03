"""Declared wrappers retain central budgets, profile preservation and privacy checks."""

import json

from agent_tools.checks import verify_llm_observations
from agent_tools.execution_settings import ActorExecutionSettings
from examples.llm_payoff_matrix import fake_response, run_llm_job
from simulation_core.behavior import ActorBehaviorSpec
from simulation_core.execution import JobManifest, JobResult
from simulation_core.model_gateway import FakeGateway
from simulation_core.request import ExperimentRequest


def wrapper_artifact():
    data = run_llm_job(gateway=FakeGateway(fake_response), rounds=1).model_dump(mode="json")
    for actor in data["manifest"]["simulation"]["world"]["actors"]:
        actor["policy_id"] = "experimental.synthetic.wrapper"
        actor["attributes"]["model_policy"] = "llm.v1"
    return data


def test_custom_llm_wrapper_uses_scheduled_budgets_and_typed_profiles():
    data = wrapper_artifact()
    config = JobResult.from_json_values(data).manifest.simulation
    settings = ActorExecutionSettings(model="central-actor")
    resolved = settings.resolve(config)
    assert settings.call_budgets(config)[0] == 4
    assert all(
        actor.policy_parameters["model"] == "central-actor"
        and actor.policy_parameters["max_calls"] == 2
        for actor in resolved.world.actors
    )
    actor = resolved.world.actors[0]
    profile = ActorBehaviorSpec(actor_id=actor.id, objective="Own payoff")
    updated = actor.model_copy(
        update={
            "policy_parameters": {
                **actor.policy_parameters,
                "behavior": profile.model_dump(mode="json"),
            }
        }
    )
    config = resolved.model_copy(
        update={
            "assumptions": (),
            "world": resolved.world.model_copy(
                update={"actors": (updated, *resolved.world.actors[1:])}
            ),
        }
    )
    JobManifest(
        request=ExperimentRequest(hypothesis="Wrapper", actor_behaviors=(profile,)),
        simulation=config,
    )
    assert verify_llm_observations(JobResult.from_json_values(data)).status == "verified"


def fallback_artifact():
    data = wrapper_artifact()
    event = data["result"]["events"][1]
    actors = {actor["id"]: actor for actor in data["manifest"]["simulation"]["world"]["actors"]}
    for decision in event["decisions"]:
        action = decision["action"]
        actors[action["actor_id"]]["attributes"]["safe_fallback_actions"] = {
            action["kind"]: action["payload"]
        }
        decision["rationale"] = "Safe fallback after two invalid structured responses."
    calls = []
    for original in event["model_calls"]:
        for attempt in (1, 2):
            call = json.loads(json.dumps(original))
            call.update(
                status="invalid_response",
                rationale=None,
                attempt=attempt,
                error_category="schema_or_json_validation",
                response_text="invalid response",
            )
            packet = json.loads(call["request"]["input_json"])
            packet["retry"] = attempt > 1
            call["request"]["input_json"] = json.dumps(packet)
            calls.append(call)
    event["model_calls"] = calls
    data["result"]["model_calls"] = calls
    return data


def test_exhausted_fallback_requires_exact_payload_and_complete_failed_trace():
    data = fallback_artifact()
    finding = verify_llm_observations(JobResult.from_json_values(data))
    assert finding.status == "verified" and finding.required
    # A fallback declaration is not permission for an arbitrary model-free choice.
    broken = json.loads(json.dumps(data))
    broken["manifest"]["simulation"]["world"]["actors"][0]["attributes"][
        "safe_fallback_actions"
    ] = {}
    assert verify_llm_observations(JobResult.from_json_values(broken)).status == "failed"
    broken = json.loads(json.dumps(data))
    broken["result"]["events"][1]["model_calls"].pop(0)
    broken["result"]["model_calls"] = broken["result"]["events"][1]["model_calls"]
    assert verify_llm_observations(JobResult.from_json_values(broken)).status == "failed"
