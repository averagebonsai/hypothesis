"""Provider protocol regressions; no credentials or network calls."""

import io
import json

import pytest

from components.gateways import openai
from components.gateways.meta import MetaResponsesGateway
from simulation_core.model_gateway import GatewayError, ModelRequest


def request():
    return ModelRequest(
        actor_id="coding",
        model="test-model",
        instructions="Return JSON",
        input_json="{}",
        response_schema={},
        response_strict=False,
        max_output_tokens=1000,
        reasoning_effort="max",
    )


def frame(value):
    return ("data: " + json.dumps(value) + "\n\n").encode()


def final(status="completed"):
    return {
        "id": "test-id",
        "model": "test-model",
        "status": status,
        "usage": {"input_tokens": 23, "output_tokens": 51},
        "incomplete_details": {"reason": "max_output_tokens"},
        "output": [
            {"type": "message", "content": [{"type": "output_text", "text": '{"ready":true}'}]}
        ],
    }


def test_stream_uses_terminal_response_and_keeps_request_stateless(monkeypatch):
    events = []

    def transport(req, timeout):
        body = json.loads(req.data)
        assert body["stream"] is True and body["store"] is False
        assert body["reasoning"]["effort"] == "max"
        assert "previous_response_id" not in body
        return io.BytesIO(
            b": heartbeat\n\n"
            + frame({"type": "response.created"})
            + frame({"type": "response.output_text.delta", "delta": "ignored duplicate"})
            + frame({"type": "response.completed", "response": final()})
        )

    monkeypatch.setattr(openai, "urlopen", transport)
    gateway = MetaResponsesGateway("fake-secret", frozenset({"test-model"}), stream=True)
    gateway.on_event = events.append
    response = gateway.complete(request())
    assert response.text == '{"ready":true}'
    assert response.input_tokens == 23 and response.output_tokens == 51
    assert events == ["response.created"]


@pytest.mark.parametrize(
    "data,category",
    [
        (frame({"type": "response.created"}), "provider_stream_interrupted"),
        (b"data: [DONE]\n\n", "provider_stream_missing_terminal"),
        (
            frame({"type": "response.incomplete", "response": final("incomplete")}),
            "provider_incomplete_max_output_tokens",
        ),
        (frame({"type": "error", "message": "must not leak"}), "provider_stream_error"),
        (b"data: invalid-json\n\n", "invalid_provider_stream"),
    ],
)
def test_stream_failures_are_explicit_and_sanitized(monkeypatch, data, category):
    monkeypatch.setattr(openai, "urlopen", lambda *a, **kw: io.BytesIO(data))
    gateway = MetaResponsesGateway("fake-secret", frozenset({"test-model"}), stream=True)
    with pytest.raises(GatewayError, match="^" + category + "$"):
        gateway.complete(request())


def test_stream_rejects_oversized_wire_frame(monkeypatch):
    monkeypatch.setattr(openai, "urlopen", lambda *a, **kw: io.BytesIO(b"data: " + b"x" * 200))
    gateway = MetaResponsesGateway(
        "fake-secret", frozenset({"test-model"}), stream=True, max_response_bytes=100
    )
    with pytest.raises(GatewayError, match="^provider_response_too_large$"):
        gateway.complete(request())
