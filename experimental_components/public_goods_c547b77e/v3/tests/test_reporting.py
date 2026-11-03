"""Offline composition and reporting checks with scripted stand-in policies."""

import json
import math

from experiment_extension.mechanism import PublicGoodsMechanism
from experiment_extension.references import zero_contribution_trajectory
from experiment_extension.report import preview, report
from experiment_extension.schemas import ContributionPayload

from agent_tools.fixtures import fixture_config
from components.library import standard_registry
from simulation_core.execution import JobManifest, JobResult
from simulation_core.reports import (
    ReportData,
    validate_explanatory_notebook,
    validate_preview_notebook,
)
from simulation_core.request import ExperimentRequest
from simulation_core.runtime import SimulationRuntime

MECHANISM_ID = "experimental.public_goods_c547b77e.public_goods.v1"
SCHEMA_ID = "experimental.public_goods_c547b77e.contribution.v1"
ACTION_KIND = "contribute"
PUBLIC_FIELDS = (
    "round",
    "rounds",
    "endowed_rounds",
    "endowment",
    "multiplier",
    "endowment_this_round",
    "balances",
    "history",
)


def scripted_config_dict(contribution=5.0):
    ids = ("p1", "p2", "p3")
    return {
        "world": {
            "actors": [
                {
                    "id": aid,
                    "kind": "participant",
                    "action_space": {"schemas": {ACTION_KIND: SCHEMA_ID}},
                    "policy_id": "scripted.v1",
                    "policy_parameters": {
                        "kind": ACTION_KIND,
                        "payload": {"contribution": contribution},
                        "memory_update": {"run_tag": "offline"},
                    },
                }
                for aid in ids
            ],
            "parameters": {
                "participant_count": 3,
                "rounds": 4,
                "endowed_rounds": 2,
                "endowment": 10.0,
                "multiplier": 1.5,
            },
            "initial_public_state": {
                "round": 1,
                "rounds": 4,
                "endowed_rounds": 2,
                "endowment": 10.0,
                "multiplier": 1.5,
                "endowment_this_round": 10.0,
                "balances": {aid: 0.0 for aid in ids},
                "history": [],
            },
        },
        "mechanism_id": MECHANISM_ID,
        "protocol_id": "simultaneous.v1",
        "protocol_parameters": {"rounds": 4},
        "permissions": {
            aid: {
                "public_fields": list(PUBLIC_FIELDS),
                "private_fields": [],
                "readable_memory": True,
                "writable_private_fields": [],
                "writable_memory": True,
            }
            for aid in ids
        },
    }


def validated_config(raw):
    config = fixture_config(raw)
    PublicGoodsMechanism().validate_config(config.world)
    return config


def registry_with_extension():
    registry = standard_registry()
    registry.mechanisms[MECHANISM_ID] = PublicGoodsMechanism
    registry.action_schemas[SCHEMA_ID] = ContributionPayload
    return registry


def run_offline(config):
    return SimulationRuntime(registry_with_extension()).run(config)


def test_offline_scripted_run():
    config = validated_config(scripted_config_dict())
    result = run_offline(config)
    assert result.status == "completed"
    assert len(result.outcomes) == 4
    committed = [event for event in result.events if event.kind == "committed"]
    assert len(committed) == 4
    opening = 0.0
    for event in committed:
        entry = event.state.public["history"][-1]
        total = sum(entry["contributions"].values())
        expected = opening + 3 * entry["endowment"] + (1.5 - 1.0) * total
        assert math.isclose(sum(event.state.public["balances"].values()), expected, rel_tol=1e-9)
        opening = sum(event.state.public["balances"].values())
        for decision in event.decisions:
            assert decision.rationale
    for aid in ("p1", "p2", "p3"):
        assert math.isclose(result.final_state.public["balances"][aid], 30.0, rel_tol=1e-9)
        assert result.final_state.private[aid].memory == {"run_tag": "offline"}
    assert result.final_state.tick == 4


def test_preview_generator_offline(tmp_path):
    config = validated_config(scripted_config_dict())
    manifest = JobManifest(
        request=ExperimentRequest(
            hypothesis="offline preview check", execution_kind="agent_simulation"
        ),
        simulation=config,
    )
    path = preview(manifest, tmp_path)
    text = path.read_text()
    validate_preview_notebook(text)
    notebook = json.loads(text)
    assert "hypothesis_report" not in notebook["metadata"]
    assert "pending" in text.lower()


def test_final_generator_binds_recorded_result(tmp_path):
    config = validated_config(scripted_config_dict())
    manifest = JobManifest(
        request=ExperimentRequest(
            hypothesis="offline report check", execution_kind="agent_simulation"
        ),
        simulation=config,
    )
    result = run_offline(config)
    artifact = JobResult(manifest=manifest, result=result, benchmark=None)
    path = report(artifact, tmp_path)
    content = path.read_text()
    validate_explanatory_notebook(content, artifact)
    notebook = json.loads(content)
    stored = ReportData.model_validate_json(json.dumps(notebook["metadata"]["hypothesis_report"]))
    names = [item.name.lower() for item in stored.references]
    assert any("zero" in name for name in names)
    assert any("reinvest" in name or "cooperat" in name for name in names)
    trajectory_figures = [figure for figure in stored.figures if len(figure.categories) == 4]
    assert len(trajectory_figures) >= 2
    for figure in trajectory_figures:
        for series in figure.series:
            assert len(series.values) == 4
        markers = [marker for marker in figure.markers if marker.position == "before"]
        assert markers
        assert any(marker.category == figure.categories[2] for marker in markers)
        assert any(
            "withdraw" in marker.label.lower() or "endow" in marker.label.lower()
            for marker in markers
        )
    # The recorded scripted run gave 5.0 every round, beating the zero reference.
    reference = zero_contribution_trajectory(
        rounds=4, endowed_rounds=2, endowment=10.0, participant_count=3
    )
    assert math.isclose(reference["final_balance_per_participant"], 20.0, rel_tol=1e-9)
    for aid in ("p1", "p2", "p3"):
        assert artifact.result.final_state.public["balances"][aid] > 20.0
