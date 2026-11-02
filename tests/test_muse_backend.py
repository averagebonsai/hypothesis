"""CLI bridge tests use data and mocked subprocesses, never live model calls."""

import json
from pathlib import Path

import pytest
from pydantic import SecretStr

from agent_tools.contracts import PlanningResponse
from agent_tools.muse import MuseCodeGateway
from extension_worker import muse
from simulation_core.model_gateway import ModelRequest


def request(stage="plan_and_tests"):
    return ModelRequest(
        actor_id="coding_agent",
        model="muse-spark-1.3",
        reasoning_effort="max",
        instructions="General coding instructions",
        input_json=json.dumps(
            {
                "stage": stage,
                "toolkit": {
                    "sources": [
                        {"path": "src/simulation_core/types.py", "content": "large source contents"}
                    ],
                    "inventory": {"policies": ["llm.v1"]},
                },
            }
        ),
        response_schema={"type": "object"},
        max_output_tokens=32000,
    )


def test_stage_keeps_current_task_and_uses_on_demand_sources(tmp_path):
    MuseCodeGateway.stage(request(), tmp_path)
    staged = json.loads((tmp_path / "inputs/task.json").read_text())
    assert staged["toolkit"]["sources"] == ["src/simulation_core/types.py"]
    assert staged["toolkit"]["source_root"] == "/opt/toolkit"
    assert "large source contents" not in (tmp_path / "inputs/task.json").read_text()
    assert sorted(p.name for p in (tmp_path / "inputs").iterdir()) == [
        "AGENTS.md",
        "response-schema.json",
        "task.json",
    ]
    assert (tmp_path / "inputs/AGENTS.md").read_text() == "General coding instructions"


def test_container_mounts_only_current_workspace_and_inputs(tmp_path):
    gateway = MuseCodeGateway(
        tmp_path, tmp_path / "audit", SecretStr("never-in-command"), sandbox="fresh"
    )
    args = gateway.arguments("run", "/tmp/fresh-stage", "sha256:image", request())
    joined = " ".join(args)
    assert "never-in-command" not in joined
    assert ".env" not in joined and "docker.sock" not in joined
    assert "experimental_components" not in joined
    assert "--privileged" not in args and "--read-only" in args
    assert "--max-model-steps" not in args
    assert "src=/tmp/fresh-stage/inputs,dst=/inputs,readonly" in joined
    assert "src=/tmp/fresh-stage/workspace,dst=/workspace" in joined
    assert "--user" in args and "10001:10001" in args


def test_assembler_reads_python_as_data_and_validates_native_plan(tmp_path, monkeypatch, plan):
    root = tmp_path / "workspace"
    inputs = tmp_path / "inputs"
    root.mkdir()
    inputs.mkdir()
    monkeypatch.setattr(muse, "ROOT", root)
    monkeypatch.setattr(muse, "INPUTS", inputs)
    (inputs / "task.json").write_text('{"stage":"plan_and_tests"}')
    data = plan.model_dump(mode="json")
    tests = data.pop("tests")
    (root / "draft.json").write_text(json.dumps(data))
    for file in tests:
        path = root / file["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(file["content"])
    muse.assemble()
    response = PlanningResponse.model_validate_json((root / "response.json").read_text())
    assert response.plan == plan
    assert response.review is None


def test_symlinked_source_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(muse, "ROOT", tmp_path)
    tests = tmp_path / "tests"
    tests.mkdir()
    other = tmp_path / "outside.py"
    other.write_text('raise RuntimeError("must never execute")')
    (tests / "test_bad.py").symlink_to(other)
    with pytest.raises(ValueError, match="symlink"):
        muse.source_files(tests, tests=True)


def test_api_backend_is_explicit_and_cli_is_default(monkeypatch, tmp_path):
    from agent_tools.authoring import CodingAgent
    from components.gateways.meta import MetaResponsesGateway

    monkeypatch.setenv("API_KEY", "fake-key")
    monkeypatch.setenv("MODEL_CODING", "muse-spark-1.3")
    project = Path(__file__).resolve().parents[1]
    cli = CodingAgent.from_environment(project, tmp_path / "cli", sandbox="fresh")
    assert isinstance(cli.gateway.gateway, MuseCodeGateway)
    assert "Write only under /workspace" in cli.instructions
    api = CodingAgent.from_environment(project, tmp_path / "api", backend="api")
    assert isinstance(api.gateway.gateway, MetaResponsesGateway)
    with pytest.raises(ValueError, match="backend"):
        CodingAgent.from_environment(project, tmp_path / "invalid", backend="unknown")


def test_initial_stdin_is_closed_and_not_part_of_command_output():
    import sys

    from agent_tools.process import bounded_command

    result = bounded_command(
        [
            sys.executable,
            "-c",
            'import sys; assert sys.stdin.read()=="test-only-key\\n"; print("ready")',
        ],
        seconds=10,
        max_bytes=1000,
        input_text="test-only-key\n",
    )
    assert result.code == 0
    assert result.stdout == "ready\n"
    assert "test-only-key" not in result.stderr
