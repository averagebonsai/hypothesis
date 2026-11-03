"""Reporting and offline composition: notebook generators plus a scripted full run.

A hand-derived all-contribute-5 trajectory grounds the fake recorded result:
rounds 1-3 pay 25 each (20-5+10), rounds 4-6 pay 5 each (0-5+10), so balances
run 25, 50, 75, 80, 85, 90. No live actor calls occur in any test here.
"""

import copy
import json

import pytest
from experiment_extension.mechanism import (
    ContributionPayload,
    PublicGoodsWithdrawalMechanism,
)
from experiment_extension.references import reference_trajectories
from experiment_extension.report import (
    build_figures,
    build_narrative,
    build_references,
    preview,
    report,
)
from test_privacy import make_simulation_dict

from agent_tools.fixtures import fixture_config
from components.policies.scripted import ScriptedPolicy
from components.protocols.simultaneous import SimultaneousProtocol
from simulation_core.execution import JobManifest, JobResult
from simulation_core.registry import ComponentRegistry
from simulation_core.reports import (
    validate_explanatory_notebook,
    validate_preview_notebook,
)
from simulation_core.runtime import SimulationRuntime
from simulation_core.types import SimulationConfig


def make_request_dict():
    behaviors = []
    for aid in ("p1", "p2", "p3"):
        behaviors.append(
            {
                "actor_id": aid,
                "objective": "Maximize your own final saved balance.",
                "behavioral_instructions": "No assigned social preference or prescribed contribution strategy. Form your own beliefs from permitted observations.",
                "background": "",
            }
        )
    return {
        "schema_version": "experiment.request.v1",
        "hypothesis": "Contribution adaptation after a known endowment withdrawal.",
        "execution_kind": "agent_simulation",
        "supplied_inputs": [
            {
                "name": "participant count",
                "value": 3,
                "target_path": "/world/parameters/participant_count",
                "source_reference": None,
            },
            {
                "name": "total rounds",
                "value": 6,
                "target_path": "/world/parameters/rounds",
                "source_reference": None,
            },
            {
                "name": "last endowed round",
                "value": 3,
                "target_path": "/world/parameters/endowed_rounds",
                "source_reference": None,
            },
            {
                "name": "early endowment per participant per round",
                "value": 20.0,
                "target_path": "/world/parameters/endowment",
                "source_reference": None,
            },
            {
                "name": "public good multiplier",
                "value": 2.0,
                "target_path": "/world/parameters/multiplier",
                "source_reference": None,
            },
        ],
        "requirements": ["offline test request"],
        "actor_behaviors": behaviors,
    }


def make_manifest():
    return JobManifest.from_json_values(
        {"request": make_request_dict(), "simulation": make_simulation_dict()}
    )


def make_artifact():
    """Fake six-round recorded result on the hand-derived all-5 trajectory."""
    manifest = make_manifest()
    balances = [25.0, 50.0, 75.0, 80.0, 85.0, 90.0]
    payoffs = [25.0, 25.0, 25.0, 5.0, 5.0, 5.0]
    base_public = manifest.simulation.world.initial_public_state
    events = [
        {
            "sequence": 0,
            "kind": "initialized",
            "state": {
                "tick": 0,
                "phase": "act",
                "public": base_public,
                "private": {aid: {"facts": {}, "memory": {}} for aid in ("p1", "p2", "p3")},
            },
        }
    ]
    history = []
    for index in range(6):
        record = {
            "round": index + 1,
            "endowment": 20.0 if index < 3 else 0.0,
            "contributions": {"p1": 5.0, "p2": 5.0, "p3": 5.0},
            "payoffs": {"p1": payoffs[index], "p2": payoffs[index], "p3": payoffs[index]},
            "balances": {
                "p1": balances[index],
                "p2": balances[index],
                "p3": balances[index],
            },
        }
        history.append(record)
        public = dict(base_public)
        public["history"] = copy.deepcopy(history)
        public["saved_balances"] = dict(record["balances"])
        events.append(
            {
                "sequence": index + 1,
                "kind": "committed",
                "state": {
                    "tick": index + 1,
                    "phase": "act" if index < 5 else "finished",
                    "public": public,
                    "private": {aid: {"facts": {}, "memory": {}} for aid in ("p1", "p2", "p3")},
                },
                "actions": [
                    {
                        "actor_id": aid,
                        "kind": "contribute",
                        "payload": {"contribution": 5.0},
                    }
                    for aid in ("p1", "p2", "p3")
                ],
                "decisions": [
                    {
                        "action": {
                            "actor_id": aid,
                            "kind": "contribute",
                            "payload": {"contribution": 5.0},
                        },
                        "rationale": f"Recorded rationale for {aid} in round {index + 1}.",
                    }
                    for aid in ("p1", "p2", "p3")
                ],
                "outcome": {
                    "payoffs": {
                        "p1": payoffs[index],
                        "p2": payoffs[index],
                        "p3": payoffs[index],
                    },
                    "metrics": {"total_contributions": 15.0},
                },
            }
        )
    return JobResult.from_json_values(
        {
            "manifest": manifest.model_dump(mode="json"),
            "result": {
                "status": "completed",
                "final_state": events[-1]["state"],
                "outcomes": [event["outcome"] for event in events[1:]],
                "events": events,
                "assumptions": [],
                "component_ids": [
                    "experimental.public_goods_fast_faae5470.mechanism",
                    "simultaneous.v1",
                ],
            },
            "benchmark": None,
        }
    )


def test_preview_leaves_results_pending(tmp_path):
    manifest = make_manifest()
    assert PublicGoodsWithdrawalMechanism().validate_config(manifest.simulation.world) is None
    path = preview(manifest, tmp_path)
    assert path.name == "preview.ipynb"
    content = path.read_text()
    validate_preview_notebook(content)
    assert "Recorded rationale" not in content
    expected = reference_trajectories(3, 6, 3, 20.0, 2.0)
    assert str(expected["full_reinvestment"][-1].balance) in content


def test_report_validates_against_recorded_result(tmp_path):
    artifact = make_artifact()
    assert (
        PublicGoodsWithdrawalMechanism().validate_config(artifact.manifest.simulation.world) is None
    )
    path = report(artifact, tmp_path)
    assert path.name == "results.ipynb"
    validate_explanatory_notebook(path.read_text(), artifact)
    assert (tmp_path / "results.ipynb").exists()


def test_figures_show_trajectories_with_withdrawal_marker():
    figures = build_figures(make_artifact())
    assert len(figures) >= 2
    for figure in figures:
        assert figure.kind == "line"
        assert len(figure.categories) == 6
    markers = [marker for figure in figures for marker in figure.markers]
    assert markers
    assert any(marker.category == "R4" and marker.position == "before" for marker in markers)
    wealth = next(figure for figure in figures if "ealth" in figure.title)
    assert len(wealth.series) == 3
    for series in wealth.series:
        assert list(series.values) == [25.0, 50.0, 75.0, 80.0, 85.0, 90.0]
    plotted = next(figure for figure in figures if "ontribution" in figure.title)
    for series in plotted.series:
        for value in series.values:
            assert ContributionPayload.model_validate({"contribution": value})


def test_references_distinguish_benchmark_scopes():
    references = build_references(make_artifact())
    assert len(references) == 2
    zero = next(ref for ref in references if "ero" in ref.name)
    coop = next(ref for ref in references if "ero" not in ref.name)
    assert "nash" in zero.explanation.lower()
    assert "not a nash equilibrium" in coop.explanation.lower()
    assert zero.payoffs["p1"] == pytest.approx(60.0)
    assert coop.payoffs["p1"] == pytest.approx(2240.0)
    expected = reference_trajectories(3, 6, 3, 20.0, 2.0)
    assert zero.payoffs["p1"] == pytest.approx(expected["zero_contribution"][-1].balance)
    assert coop.payoffs["p1"] == pytest.approx(expected["full_reinvestment"][-1].balance)


def test_narrative_assumptions_avoid_config_dumps():
    artifact = make_artifact()
    assert (
        PublicGoodsWithdrawalMechanism().validate_config(artifact.manifest.simulation.world) is None
    )
    narrative = build_narrative(artifact)
    assert narrative.title and narrative.background and narrative.interpretation
    assert len(narrative.assumptions) >= 1
    assert len(narrative.limitations) >= 1
    for item in narrative.assumptions:
        assert "/world/" not in item
        assert "```" not in item
    assert "```json" not in narrative.interpretation.lower()


def test_report_cells_never_repeat_actor_calls(tmp_path):
    artifact = make_artifact()
    path = report(artifact, tmp_path)
    text = path.read_text()
    assert "choose_action" not in text
    assert "Recorded rationale for p1 in round 1" not in text
    assert set(ContributionPayload.model_json_schema()["required"]) == {"contribution"}


def make_scripted_config():
    simulation = make_simulation_dict()
    for actor in simulation["world"]["actors"]:
        actor["policy_id"] = "scripted.v1"
        actor["policy_parameters"] = {
            "kind": "contribute",
            "payload": {"contribution": 5.0},
            "required_fields": [],
        }
    return fixture_config(simulation)


def make_registry():
    registry = ComponentRegistry()
    registry.mechanisms["experimental.public_goods_fast_faae5470.mechanism"] = (
        PublicGoodsWithdrawalMechanism
    )
    registry.protocols["simultaneous.v1"] = SimultaneousProtocol
    registry.policies["scripted.v1"] = lambda params: ScriptedPolicy(params)
    registry.action_schemas["experimental.public_goods_fast_faae5470.contribution"] = (
        ContributionPayload
    )
    return registry


def test_offline_scripted_run_matches_hand_derived_trajectory():
    config = make_scripted_config()
    assert isinstance(config, SimulationConfig)
    assert PublicGoodsWithdrawalMechanism.requires_joint_actions is True
    assert ContributionPayload.model_validate({"contribution": 5.0}).contribution == 5.0
    runtime = SimulationRuntime(make_registry())
    result = runtime.run(config)
    assert result.status == "completed"
    assert len(result.outcomes) == 6
    assert result.final_state.public["saved_balances"] == {
        "p1": 90.0,
        "p2": 90.0,
        "p3": 90.0,
    }
    assert len(result.final_state.public["history"]) == 6
    assert [event.state.tick for event in result.events[1:]] == [1, 2, 3, 4, 5, 6]
    assert list(result.model_calls) == []
    assert json.loads(config.model_dump_json())["world"]["parameters"]["rounds"] == 6
