"""Experiment-local lifecycle and continuation, with no model/provider calls."""

import json

import pytest
from pydantic import SecretStr

from agent_tools.muse import AUTH_FRAME, RESULT_FRAME, MuseCodeGateway
from agent_tools.process import ProcessResult
from extension_worker.muse import begin_stage
from simulation_core.model_gateway import ModelRequest, ModelResponse


def request(stage, experiment="current", **extra):
    task = {"stage": stage, "request": {"hypothesis": "Same experiment"}, **extra}
    if stage == "plan_and_tests":
        task["experiment_id"] = experiment
    else:
        task["frozen_plan"] = {"bundle": {"experiment_id": experiment}, "tests": []}
    return ModelRequest(
        actor_id="coding_agent",
        model="model",
        instructions="Instructions",
        input_json=json.dumps(task),
        response_schema={},
        max_output_tokens=100,
    )


def mock_transport(monkeypatch, gateway, commands):
    import agent_tools.muse as module

    def command(args, **kwargs):
        commands.append(args)
        if "inspect" in args:
            return ProcessResult(0, "true " + gateway.session_id, "")
        if "exchange" in kwargs:
            exchange = kwargs["exchange"]
            assert "synthetic" in exchange(AUTH_FRAME)
            exchange(RESULT_FRAME + ModelResponse(text="{}", model="model").model_dump_json())
        return ProcessResult(0, "", "")

    monkeypatch.setattr(module, "bounded_command", command)
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: None)


def test_stages_share_one_session_container_and_volumes_then_close(monkeypatch, tmp_path):
    gateway = MuseCodeGateway(tmp_path, tmp_path / "audit", SecretStr("synthetic"))
    gateway.prepared = {"image_id": "image", "framework_digest": "digest"}
    commands = []
    mock_transport(monkeypatch, gateway, commands)
    for stage in ("plan_and_tests", "implementation", "repair_implementation"):
        gateway.complete(request(stage))
    starts = [args for args in commands if "--detach" in args]
    executions = [args for args in commands if "--interactive" in args]
    assert len(starts) == 1 and len(executions) == 3
    assert all(gateway.session_id == args[-1] for args in executions)
    assert not any("stop" in args for args in commands)
    assert len([args for args in commands if "update-session" in args]) == 3
    gateway.close()
    gateway.close()  # idempotent
    assert len([args for args in commands if args[1:3] == ["rm", "--force"]]) == 1
    assert len([args for args in commands if args[1:3] == ["volume", "rm"]]) == 3
    with pytest.raises(RuntimeError, match="closed"):
        gateway.complete(request("implementation"))


def test_new_experiments_cannot_inherit_or_select_another_experiments_session(
    monkeypatch, tmp_path
):
    first = MuseCodeGateway(tmp_path, tmp_path / "first", SecretStr("synthetic"))
    second = MuseCodeGateway(tmp_path, tmp_path / "second", SecretStr("synthetic"))
    assert first.session_id != second.session_id
    assert first.volume("home") != second.volume("home")
    first.prepared = {"image_id": "image"}
    commands = []
    mock_transport(monkeypatch, first, commands)
    first.complete(request("plan_and_tests"))
    with pytest.raises(ValueError, match="across experiments"):
        first.complete(request("implementation", experiment="another"))
    assert len([args for args in commands if "--interactive" in args]) == 1
    with pytest.raises(ValueError, match="explicitly resume"):
        MuseCodeGateway(tmp_path, tmp_path / "first", SecretStr("synthetic"))
    resumed = MuseCodeGateway(tmp_path, tmp_path / "first", SecretStr("synthetic"), resume=True)
    assert resumed.session_id == first.session_id
    resumed.complete(request("implementation"))
    assert len([args for args in commands if "--detach" in args]) == 1
    resumed.close()
    first.close()


def test_two_controllers_cannot_update_one_session_concurrently(tmp_path):
    first = MuseCodeGateway(tmp_path, tmp_path / "audit", SecretStr("synthetic"))
    second = MuseCodeGateway(tmp_path, tmp_path / "audit", SecretStr("synthetic"))
    with first._exclusive():
        with pytest.raises(RuntimeError, match="already running"):
            second.complete(request("plan_and_tests"))
        with pytest.raises(RuntimeError, match="already running"):
            second.close()


def test_stage_discards_stale_responses_but_retains_notes_and_prototypes(monkeypatch, tmp_path):
    from extension_worker import muse

    monkeypatch.setattr(muse, "ROOT", tmp_path)
    for name in ("response.json", "review.json", "decision-notes.md", "prototype.py"):
        (tmp_path / name).write_text("previous stage content")
    begin_stage()
    assert not (tmp_path / "response.json").exists() and not (tmp_path / "review.json").exists()
    assert (tmp_path / "decision-notes.md").read_text() == "previous stage content"
    assert (tmp_path / "prototype.py").exists()


def test_unavailable_session_refuses_silent_fresh_start(monkeypatch, tmp_path):
    gateway = MuseCodeGateway(tmp_path, tmp_path / "audit", SecretStr("synthetic"))
    gateway.prepared = {"image_id": "image"}
    commands = []
    mock_transport(monkeypatch, gateway, commands)
    gateway.complete(request("plan_and_tests"))
    import agent_tools.muse as module

    monkeypatch.setattr(
        module, "bounded_command", lambda *args, **kwargs: ProcessResult(1, "", "missing")
    )
    with pytest.raises(RuntimeError, match="silent context reset"):
        gateway.complete(request("implementation"))
