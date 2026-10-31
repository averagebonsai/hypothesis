import io
import json

import pytest

from components.gateways.settings import LiveModelSettings
from examples.llm_payoff_matrix import fake_response, run_llm_job
from simulation_core.logging import replay, stream_action_trace
from simulation_core.model_gateway import FakeGateway


@pytest.mark.parametrize("rationale", [None, "", "   "])
def test_llm_rejects_missing_explanation_before_commit(rationale):
    def respond(request):
        payload = json.loads(fake_response(request))
        payload["rationale"] = rationale
        return json.dumps(payload)

    from components.policies.llm import LLMPolicyError

    with pytest.raises(LLMPolicyError) as error:
        run_llm_job(gateway=FakeGateway(respond))
    assert all(record.status == "invalid_response" for record in error.value.records)
    assert all(record.rationale is None for record in error.value.records)


def test_each_committed_action_has_rationale_console_trace_and_call_link():
    output = io.StringIO()
    with stream_action_trace(output):
        artifact = run_llm_job(rounds=2)
    lines = [json.loads(line) for line in output.getvalue().splitlines()]
    assert len(lines) == 4
    assert [(line["tick"], line["actor_id"]) for line in lines] == [
        (1, "A"),
        (1, "B"),
        (2, "A"),
        (2, "B"),
    ]
    for event in artifact.result.events[1:]:
        assert tuple(decision.action for decision in event.decisions) == event.actions
        accepted = {call.actor_id: call for call in event.model_calls if call.status == "accepted"}
        for decision in event.decisions:
            assert decision.rationale
            assert decision.rationale == accepted[decision.action.actor_id].rationale
    assert replay(artifact.result.events)[-1] == artifact.result.final_state
    assert all(line["rationale"] for line in lines)


def clean_environment(monkeypatch):
    for name in ("API_KEY", "MODEL", "OPENAI_API_KEY", "OPENAI_MODEL"):
        monkeypatch.delenv(name, raising=False)


def test_env_file_aliases_are_loaded_without_exposing_credentials(tmp_path, monkeypatch):
    clean_environment(monkeypatch)
    path = tmp_path / ".env"
    path.write_text('API_KEY="test-secret-never-log"\nMODEL=test-model\n')
    settings = LiveModelSettings.load(env_file=path)
    assert settings.model == "test-model"
    assert settings.api_key.get_secret_value() == "test-secret-never-log"
    assert "test-secret-never-log" not in repr(settings)
    assert "test-secret-never-log" not in settings.model_dump_json()
    monkeypatch.setenv("API_KEY", "environment-secret")
    monkeypatch.setenv("MODEL", "environment-model")
    assert LiveModelSettings.load(env_file=path).model == "environment-model"
    assert LiveModelSettings.load(env_file=path).api_key.get_secret_value() == "environment-secret"
    assert LiveModelSettings.load(model="explicit", env_file=path).model == "explicit"


def test_missing_credentials_and_standard_names(tmp_path, monkeypatch):
    clean_environment(monkeypatch)
    with pytest.raises(ValueError, match="API_KEY"):
        LiveModelSettings.load(env_file=tmp_path / "absent")
    monkeypatch.setenv("OPENAI_API_KEY", "test-standard-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-standard-model")
    assert LiveModelSettings.load(env_file=tmp_path / "absent").model == "test-standard-model"


def test_replay_rejects_inconsistent_explanation_link():
    artifact = run_llm_job()
    event = artifact.result.events[1]
    changed = event.decisions[0].model_copy(update={"rationale": "A different explanation"})
    changed_event = event.model_copy(update={"decisions": (changed, *event.decisions[1:])})
    with pytest.raises(ValueError, match="rationale"):
        replay((artifact.result.events[0], changed_event))


def test_meta_transport_uses_documented_endpoint_and_reasoning_setting(monkeypatch):
    from components.gateways import openai
    from components.gateways.meta import MetaResponsesGateway
    from simulation_core.model_gateway import ModelRequest

    def fake_urlopen(request, timeout):
        assert request.full_url == "https://api.meta.ai/v1/responses"
        body = json.loads(request.data)
        assert body["model"] == "muse-spark-1.3-contributor"
        assert body["reasoning"]["effort"] == "low"
        return io.BytesIO(
            json.dumps(
                {
                    "status": "completed",
                    "id": "meta-test",
                    "model": body["model"],
                    "output": [
                        {"type": "message", "content": [{"type": "output_text", "text": "{}"}]}
                    ],
                }
            ).encode()
        )

    monkeypatch.setattr(openai, "urlopen", fake_urlopen)
    response = MetaResponsesGateway(
        "dummy-test-key", frozenset({"muse-spark-1.3-contributor"})
    ).complete(
        ModelRequest(
            actor_id="A",
            model="muse-spark-1.3-contributor",
            reasoning_effort="low",
            instructions="test",
            input_json="{}",
            response_schema={"type": "object", "properties": {}, "additionalProperties": False},
            max_output_tokens=1000,
        )
    )
    assert response.request_id == "meta-test"
