"""Tool-only jobs exercise a callable, never an actor/protocol simulation."""

from pathlib import Path

from agent_tools.jobs import ToolJobManifest
from extension_worker.runtime import load_registry
from extension_worker.tools import execute_tool


def test_tool_integrates_without_simulation():
    bundle, _ = load_registry(Path("/bundle"))
    job = ToolJobManifest.model_validate_json(Path("/job/manifest.json").read_text())
    result = execute_tool(job, bundle)
    assert result.manifest == job
    assert type(result).model_validate_json(result.model_dump_json()) == result
