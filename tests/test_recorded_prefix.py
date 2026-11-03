import pytest

from agent_tools.replay_gateway import RecordedPrefixGateway
from simulation_core.model_gateway import FakeGateway, GatewayError, ModelRequest, ModelResponse


def test_reuse_preserves_original_response_and_queries_only_missing_decisions():
    request = ModelRequest(
        actor_id="p1",
        model="model",
        instructions="Rules",
        input_json='{"round":1}',
        response_schema={},
        max_output_tokens=100,
    )
    response = ModelResponse(text="original action", model="model", request_id="original-id")
    provider = FakeGateway(lambda _: "new action")
    gateway = RecordedPrefixGateway(provider, ((request, response),))
    assert gateway.complete(request).request_id == "original-id"
    assert gateway.last_replayed and provider.requests == []
    changed = request.model_copy(update={"input_json": '{"round":2}'})
    assert gateway.complete(changed).text == "new action"
    assert not gateway.last_replayed and len(provider.requests) == 1


def test_changed_observation_never_reuses_or_calls_provider():
    request = ModelRequest(
        actor_id="p1",
        model="model",
        instructions="Rules",
        input_json='{"round":1}',
        response_schema={},
        max_output_tokens=100,
    )
    provider = FakeGateway(lambda _: "must not call")
    gateway = RecordedPrefixGateway(
        provider, ((request, ModelResponse(text="old", model="model")),)
    )
    with pytest.raises(GatewayError, match="mismatch"):
        gateway.complete(request.model_copy(update={"input_json": '{"round":2}'}))
    assert provider.requests == [] and gateway.index == 0


def test_budget_removal_retains_authentic_original_request_and_failed_attempt():
    old = ModelRequest(
        actor_id="p1",
        model="model",
        instructions="Rules",
        input_json='{"retry":false}',
        response_schema={},
        max_output_tokens=4096,
    )
    provider = FakeGateway(lambda _: "new")
    gateway = RecordedPrefixGateway(
        provider,
        ((old, GatewayError("provider_incomplete_max_output_tokens", output_tokens=4096)),),
        allow_output_budget_change=True,
    )
    with pytest.raises(GatewayError) as caught:
        gateway.complete(old.model_copy(update={"max_output_tokens": None}))
    assert caught.value.recorded_request["max_output_tokens"] == 4096
    assert caught.value.output_tokens == 4096 and gateway.last_replayed
    assert provider.requests == []
