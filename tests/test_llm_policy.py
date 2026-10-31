import io
import json
import os
from urllib.error import HTTPError

import pytest

from components.gateways.openai import OpenAIResponsesGateway, strict_schema
from components.mechanisms.normal_form import MovePayload
from components.mechanisms.recording import NumericPayload
from components.policies.llm import LLMPolicy, LLMPolicyError
from examples.llm_payoff_matrix import fake_response, run_live_job, run_llm_job
from simulation_core.execution import JobResult
from simulation_core.logging import replay
from simulation_core.model_gateway import BoundedGateway, FakeGateway, GatewayError
from simulation_core.types import Observation, PrivateState


def observation():
    return Observation(
        actor_id="A",
        phase="act",
        visible={"instructions": "choose"},
        private=PrivateState(facts={"secret": "own-secret"}),
        allowed_action_kinds=("choose_move",),
    )


def policy(callback, **overrides):
    gateway = FakeGateway(callback)
    instance = LLMPolicy(
        {"model": "fake-model", "instructions": "Choose a move.", **overrides},
        BoundedGateway(gateway),
        {"choose_move": MovePayload},
    )
    return instance, gateway


def test_generic_policy_numeric_action_and_private_memory_updates():
    def respond(request):
        return json.dumps(
            {
                "action": {"actor_id": "north", "kind": "measure", "payload": {"value": 2.5}},
                "memory_update": [{"key": "nested", "value_json": '{"readings": [2.5]}'}],
                "private_updates": [{"key": "calibrated", "value_json": "true"}],
                "rationale": "Return configured test value.",
            }
        )

    instance = LLMPolicy(
        {"model": "fake", "instructions": "Measure."},
        FakeGateway(respond),
        {"measure": NumericPayload},
    )
    obs = Observation(
        actor_id="north",
        phase="record",
        visible={},
        private=PrivateState(),
        allowed_action_kinds=("measure",),
        writable_private_fields=("calibrated",),
    )
    result = instance.choose_action(obs)
    assert result.action.payload == {"value": 2.5}
    assert result.memory_update == {"nested": {"readings": [2.5]}}
    assert result.private_updates == {"calibrated": True}


def test_invalid_json_retried_and_records_are_preserved():
    count = 0

    def respond(request):
        nonlocal count
        count += 1
        return "not-json" if count == 1 else fake_response(request)

    instance, gateway = policy(respond)
    result = instance.choose_action(observation())
    assert result.action.actor_id == "A"
    assert [record.status for record in instance.model_calls()] == ["invalid_response", "accepted"]
    assert json.loads(gateway.requests[1].input_json)["retry"] is True


@pytest.mark.parametrize(
    "failure", ["actor", "kind", "payload", "memory", "duplicate", "nan", "private"]
)
def test_invalid_decisions_fail_within_budget(failure):
    def respond(request):
        response = json.loads(fake_response(request))
        if failure == "actor":
            response["action"]["actor_id"] = "B"
        elif failure == "kind":
            response["action"]["kind"] = "exit"
        elif failure == "payload":
            response["action"]["payload"]["extra"] = True
        elif failure == "memory":
            response["memory_update"] = [{"key": "x", "value_json": "1"}]
        elif failure == "duplicate":
            response["memory_update"] = [{"key": "x", "value_json": "1"}] * 2
        elif failure == "nan":
            response["memory_update"] = [{"key": "x", "value_json": "NaN"}]
        else:
            response["private_updates"] = [{"key": "another_actor", "value_json": "1"}]
        return json.dumps(response)

    instance, gateway = policy(respond, max_attempts=2)
    obs = observation()
    if failure == "memory":
        obs = obs.model_copy(update={"writable_memory": False})
    with pytest.raises(LLMPolicyError) as error:
        instance.choose_action(obs)
    assert len(gateway.requests) == 2
    assert all(record.status == "invalid_response" for record in error.value.records)


def test_per_actor_and_shared_gateway_call_budgets():
    instance, gateway = policy(lambda _: "bad", max_attempts=5, max_calls=1)
    with pytest.raises(LLMPolicyError):
        instance.choose_action(observation())
    assert len(gateway.requests) == 1
    shared = BoundedGateway(FakeGateway(fake_response), max_calls=1)
    instance = LLMPolicy(
        {"model": "fake", "instructions": "choose"}, shared, {"choose_move": MovePayload}
    )
    instance.choose_action(observation())
    with pytest.raises(LLMPolicyError) as error:
        instance.choose_action(observation())
    assert shared.calls == 1
    assert error.value.records[-1].error_category == "call_budget_exhausted"


def test_gateway_size_and_output_limits():
    instance, gateway = policy(fake_response)
    instance.choose_action(observation())
    request = gateway.requests[0]
    for limits, category in [
        ({"max_request_chars": 1}, "request_too_large"),
        ({"max_output_tokens_per_call": 1}, "output_budget_exceeded"),
        ({"max_response_chars": 1}, "response_too_large"),
    ]:
        with pytest.raises(GatewayError, match=category):
            BoundedGateway(FakeGateway(fake_response), **limits).complete(request)


def test_full_job_privacy_simultaneity_replay_and_provenance():
    transport = FakeGateway(fake_response)
    artifact = run_llm_job(gateway=transport, rounds=2)
    assert artifact.result.status == "completed"
    assert len(artifact.result.model_calls) == 4
    assert len(artifact.result.events[1].model_calls) == 2
    assert all(record.mode == "fake" for record in artifact.result.model_calls)
    first = [json.loads(request.input_json)["observation"] for request in transport.requests[:2]]
    assert first[0]["visible"] == first[1]["visible"]
    assert first[0]["visible"]["history"] == []
    assert all(obs["private"] == {"facts": {}, "memory": {}} for obs in first)
    second = json.loads(transport.requests[2].input_json)["observation"]
    assert second["private"]["memory"] == {"last_move": "cooperate"}
    calls_before = len(transport.requests)
    assert replay(artifact.result.events)[-1] == artifact.result.final_state
    assert len(transport.requests) == calls_before
    assert JobResult.model_validate_json(artifact.model_dump_json()) == artifact


def provider_request():
    instance, gateway = policy(fake_response)
    instance.choose_action(observation())
    return gateway.requests[0]


def provider_response(text):
    return {
        "id": "resp-test",
        "model": "resolved-model",
        "status": "completed",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
        "usage": {"input_tokens": 20, "output_tokens": 30},
    }


def test_openai_transport_mocked_no_live_request(monkeypatch):
    from components.gateways import openai

    request = provider_request()

    def fake_urlopen(http_request, timeout):
        assert http_request.full_url == "https://api.openai.com/v1/responses"
        assert timeout == 45.0
        body = json.loads(http_request.data)
        assert body["store"] is False
        assert body["text"]["format"]["strict"] is True
        assert body["max_output_tokens"] == request.max_output_tokens
        return io.BytesIO(json.dumps(provider_response(fake_response(request))).encode())

    monkeypatch.setattr(openai, "urlopen", fake_urlopen)
    gateway = OpenAIResponsesGateway("unit-test-secret", frozenset({request.model}))
    response = gateway.complete(request)
    assert response.request_id == "resp-test"
    assert response.model == "resolved-model"
    assert response.input_tokens == 20 and response.output_tokens == 30
    assert "unit-test-secret" not in request.model_dump_json()
    with pytest.raises(GatewayError, match="model_not_allowed"):
        gateway.complete(request.model_copy(update={"model": "other-model"}))
    strict = strict_schema(request.response_schema)
    assert strict["additionalProperties"] is False


@pytest.mark.parametrize("status", ["refusal", "incomplete", "empty", "oversized", "http"])
def test_provider_failures_are_sanitized(monkeypatch, status):
    from components.gateways import openai

    request = provider_request()
    response = provider_response(fake_response(request))
    if status == "refusal":
        response["output"] = [
            {"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}
        ]
    elif status == "incomplete":
        response["status"] = "incomplete"
    elif status == "empty":
        response["output"] = []

    def fake_urlopen(*args, **kwargs):
        if status == "http":
            raise HTTPError("url", 401, "unit-test-secret", {}, None)
        return io.BytesIO(json.dumps(response).encode())

    monkeypatch.setattr(openai, "urlopen", fake_urlopen)
    gateway = OpenAIResponsesGateway(
        "unit-test-secret",
        frozenset({request.model}),
        max_response_bytes=1 if status == "oversized" else 200000,
    )
    with pytest.raises(GatewayError) as error:
        gateway.complete(request)
    assert "unit-test-secret" not in str(error.value)


@pytest.mark.skipif(os.environ.get("RUN_LIVE_LLM_TEST") != "1", reason="Live API test is opt-in")
def test_live_openai_smoke():
    artifact = run_live_job()
    assert artifact.result.status == "completed"
    assert all(call.mode == "live" for call in artifact.result.model_calls)
    assert artifact.benchmark.result.status == "solved"


def test_schema_adapter_preserves_property_names_and_converts_constants():
    schema = {
        "type": "object",
        "properties": {
            "default": {"type": "string", "default": "value"},
            "actor": {"type": "string", "const": "A"},
        },
        "additionalProperties": False,
    }
    strict = strict_schema(schema)
    assert "default" in strict["properties"]
    assert "default" not in strict["properties"]["default"]
    assert strict["properties"]["actor"]["enum"] == ["A"]
    assert schema["properties"]["actor"]["const"] == "A"


def test_multiple_action_kinds_use_their_own_payload_schemas():
    def respond(request):
        return json.dumps(
            {
                "action": {"actor_id": "A", "kind": "measure", "payload": {"value": 3.0}},
                "memory_update": None,
                "private_updates": [],
                "rationale": "Choose the numeric action for this schema test.",
            }
        )

    instance = LLMPolicy(
        {"model": "fake", "instructions": "Choose."},
        FakeGateway(respond),
        {"choose_move": MovePayload, "measure": NumericPayload},
    )
    obs = observation().model_copy(update={"allowed_action_kinds": ("choose_move", "measure")})
    assert instance.choose_action(obs).action.payload == {"value": 3.0}
