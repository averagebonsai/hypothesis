"""Observable progress and recovery use synthetic events, never historical runs."""

import json

import pytest
from pydantic import SecretStr

from agent_tools.muse import AUTH_FRAME, RESULT_FRAME, MuseCodeGateway
from agent_tools.process import ProcessLimitError, ProcessResult
from agent_tools.progress import AuthoringProgress
from extension_worker.muse import snapshot_workspace
from simulation_core.model_gateway import ModelRequest, ModelResponse


def request(**task):
    return ModelRequest(
        actor_id="coding_agent",
        model="model",
        instructions="Generic instructions",
        input_json=json.dumps({"stage": "implementation", **task}),
        response_schema={},
        max_output_tokens=100,
    )


def test_progress_summarizes_tools_retries_heartbeats_and_cumulative_usage(tmp_path):
    now = [0.0]
    messages = []
    progress = AuthoringProgress(
        tmp_path / "progress.jsonl", "planning", emit=messages.append, clock=lambda: now[0]
    )
    progress.consume(
        {"payload_type": "run.output.delta", "payload": {"text": "should not be printed"}}
    )
    progress.consume(
        {
            "payload_type": "tool.result",
            "payload": {
                "correlation_facts": {"tool_name": "bash", "outcome": "success"},
                "text": json.dumps({"description": "Check source syntax"}),
            },
        }
    )
    progress.consume(
        {
            "payload_type": "task.lifecycle.status",
            "payload": {
                "event": {
                    "message": "Stream disconnected; retrying",
                    "details": {"phase": "retrying"},
                }
            },
        }
    )
    for count in (1, 2):
        progress.consume(
            {
                "payload_type": "run.usage",
                "payload": {
                    "run_stream": {"id": "same"},
                    "calls": count,
                    "completed_calls": count,
                    "models": [{"input_tokens": 10 * count, "output_tokens": count}],
                },
            }
        )
    now[0] = 31
    progress.tick()
    assert progress.usage()["calls"] == 2 and progress.usage()["input_tokens"] == 20
    assert progress.tools == 1 and progress.retries == 1
    assert "Check source syntax" in "\n".join(messages)
    assert "should not be printed" not in "\n".join(messages)
    assert (
        json.loads((tmp_path / "progress.jsonl").read_text().splitlines()[-1])["kind"]
        == "heartbeat"
    )
    assert (tmp_path / "progress.jsonl").stat().st_mode & 0o777 == 0o600


def test_staging_materializes_only_current_trial_files(tmp_path):
    test = {"path": "tests/test_current.py", "content": "def test_current(): pass\n"}
    code = {"path": "experiment_extension/current.py", "content": "value = 1\n"}
    MuseCodeGateway.stage(
        request(frozen_plan={"tests": [test]}, previous_implementation={"files": [code]}),
        tmp_path,
        execution_capabilities={"live_actor_relay": True},
    )
    assert (tmp_path / "inputs/frozen_tests/tests/test_current.py").read_text() == test["content"]
    assert (tmp_path / "workspace/experiment_extension/current.py").read_text() == code["content"]
    data = json.loads((tmp_path / "inputs/task.json").read_text())
    assert data["execution_capabilities"]["live_actor_relay"] is True
    assert (tmp_path / "workspace/experiment_extension/current.py").stat().st_mode & 0o222 == 0o222


def test_snapshot_is_bounded_data_only_and_excludes_unrelated_files(tmp_path):
    package = tmp_path / "experiment_extension"
    package.mkdir()
    (package / "current.py").write_text('raise RuntimeError("do not import")')
    (tmp_path / "unrelated.txt").write_text("not an artifact")
    assert snapshot_workspace(tmp_path) == {
        "experiment_extension/current.py": 'raise RuntimeError("do not import")'
    }
    (package / "link.py").symlink_to(tmp_path / "unrelated.txt")
    with pytest.raises(ValueError, match="symlink"):
        snapshot_workspace(tmp_path)


@pytest.mark.parametrize("failed", [False, True])
def test_cli_usage_propagation_and_partial_recovery(monkeypatch, tmp_path, failed):
    import agent_tools.muse as module

    gateway = MuseCodeGateway(tmp_path, tmp_path / "audit", SecretStr("synthetic-key-789"))
    gateway.prepared = {"image_id": "image", "framework_digest": "digest"}

    def command(args, **kwargs):
        if args[-1] == "snapshot":
            return ProcessResult(0, json.dumps({"experiment_extension/partial.py": "value=1"}), "")
        if "exchange" not in kwargs:
            return ProcessResult(0, "", "")
        exchange = kwargs["exchange"]
        assert "synthetic-key-789" in exchange(AUTH_FRAME)
        exchange(
            json.dumps(
                {
                    "payload_type": "run.usage",
                    "payload": {
                        "run_stream": {"id": "one"},
                        "calls": 3,
                        "completed_calls": 3,
                        "models": [{"input_tokens": 42, "output_tokens": 17}],
                    },
                }
            )
        )
        if failed:
            raise ProcessLimitError("synthetic timeout")
        exchange(RESULT_FRAME + ModelResponse(text="{}", model="model").model_dump_json())
        return ProcessResult(0, "", "")

    monkeypatch.setattr(module, "bounded_command", command)
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: None)
    if failed:
        with pytest.raises(ProcessLimitError):
            gateway.complete(request())
        partial = json.loads(
            next((tmp_path / "audit").glob("*/partial_workspace.json")).read_text()
        )
        assert partial["status"] == "unapproved"
        assert "experiment_extension/partial.py" in partial["files"]
        assert list((tmp_path / "audit").glob("*/failure.json"))
    else:
        response = gateway.complete(request())
        assert response.input_tokens == 42 and response.output_tokens == 17
    log = next((tmp_path / "audit").glob("*/native-events.jsonl")).read_text()
    assert "synthetic-key-789" not in log and "run.usage" in log
