import json
import shutil
from pathlib import Path

import pytest

from agent_tools.authoring import (
    SOURCE_FILES,
    CodingAgent,
    Implementation,
    SourceFile,
    build_context,
    safe_source_path,
)
from simulation_core.model_gateway import FakeGateway

PROJECT = Path(__file__).resolve().parents[1]


def test_clean_context_excludes_history_results_tests_and_private_files(tmp_path):
    for relative in SOURCE_FILES:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT / relative, path)
    marker = "PRIVATE_EVALUATION_TRIPWIRE_MUST_NOT_REACH_MODEL"
    for relative in (
        "experimental_components/prior/v1/README.md",
        "experimental_components/allocation_trial/v2/experiment_extension/solver.py",
        "experimental_components/vector_allocation/v1/experiment_extension/allocation.py",
        "docs/TRIAL.md",
        "tests/private_answer.py",
        ".env",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(marker)
    context = build_context(tmp_path)
    assert marker not in json.dumps(context)
    assert all(
        not item["path"].startswith(("experimental_components/", "tests/", "docs/"))
        for item in context["sources"]
    )


def test_source_paths_cannot_escape_authoring_package():
    assert safe_source_path("experiment_extension/module.py", tests=False)
    for path in (
        "../src/hack.py",
        "/tmp/hack.py",
        "experiment_extension/../../src/hack.py",
        "tests/test_hack.py",
        ".env",
    ):
        assert not safe_source_path(path, tests=False)
    assert safe_source_path("tests/test_new.py", tests=True)


def test_model_call_is_fresh_auditable_and_has_no_implicit_history(tmp_path):
    gateway = FakeGateway(
        lambda request: Implementation(
            summary="Generated implementation",
            files=(SourceFile(path="experiment_extension/__init__.py", content=""),),
        ).model_dump_json()
    )
    agent = CodingAgent(PROJECT, gateway, "fake-model", tmp_path / "audit")
    result = agent.call(
        {"stage": "implementation", "request": {"hypothesis": "Fresh request"}}, Implementation
    )
    assert isinstance(result, Implementation)
    request = gateway.requests[0]
    assert "vector_allocation" not in request.input_json
    assert "allocation_trial" not in request.input_json
    assert "project_simplex" not in request.input_json
    assert not hasattr(request, "previous_response_id")
    manifest = json.loads((tmp_path / "audit/context_manifest.json").read_text())
    assert "no filesystem" in manifest["access"].lower()
    assert (tmp_path / "audit/request-1.json").stat().st_mode & 0o777 == 0o600


def test_context_source_links_are_rejected(tmp_path):
    path = tmp_path / SOURCE_FILES[0]
    path.parent.mkdir(parents=True)
    path.symlink_to(PROJECT / SOURCE_FILES[0])
    with pytest.raises(ValueError, match="symbolic"):
        build_context(tmp_path)


def test_resume_preserves_api_budget_and_original_requests(tmp_path):
    gateway = FakeGateway(
        lambda request: Implementation(
            summary="A new artifact",
            files=(SourceFile(path="experiment_extension/__init__.py", content=""),),
        ).model_dump_json()
    )
    audit = tmp_path / "audit"
    first = CodingAgent(PROJECT, gateway, "fake-model", audit, max_calls=5)
    first.call({"stage": "implementation"}, Implementation)
    original = (audit / "request-1.json").read_bytes()
    resumed = CodingAgent(PROJECT, gateway, "fake-model", audit, resume=True, max_calls=5)
    assert resumed.gateway.calls == 1
    for _ in range(4):
        resumed.call({"stage": "repair_implementation"}, Implementation)
    with pytest.raises(ValueError, match="budget"):
        resumed.call({"stage": "repair_implementation"}, Implementation)
    assert len(gateway.requests) == 5
    assert not (audit / "request-6.json").exists()
    assert (audit / "request-1.json").read_bytes() == original
    with pytest.raises(ValueError, match="budget"):
        CodingAgent(PROJECT, gateway, "fake-model", audit, resume=True, max_calls=5)


def test_coding_agent_has_no_default_turn_limit_and_resume_keeps_count(tmp_path):
    gateway = FakeGateway(
        lambda request: Implementation(
            summary="A synthetic artifact",
            files=(SourceFile(path="README.md", content=""),),
        ).model_dump_json()
    )
    agent = CodingAgent(PROJECT, gateway, "fake-model", tmp_path / "audit")
    for _ in range(8):
        agent.call({"stage": "implementation"}, Implementation)
    resumed = CodingAgent(PROJECT, gateway, "fake-model", tmp_path / "audit", resume=True)
    resumed.call({"stage": "implementation"}, Implementation)
    assert resumed.gateway.max_calls is None
    assert resumed.gateway.calls == 9
    assert len(gateway.requests) == 9


def test_resume_rejects_tampered_context(tmp_path):
    audit = tmp_path / "audit"
    gateway = FakeGateway(lambda request: "{}")
    CodingAgent(PROJECT, gateway, "fake-model", audit)
    path = audit / "context_manifest.json"
    data = json.loads(path.read_text())
    data["instructions_sha256"] = "tampered"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="changed"):
        CodingAgent(PROJECT, gateway, "fake-model", audit, resume=True)
