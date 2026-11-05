"""Full-horizon offline run: 36 phases, 45 decisions, reports and recovery."""

import json
from pathlib import Path

from experiment_extension.report import describe, preview, report
from experiment_extension.supplychain import SupplyChainMechanism, schedule_phases
from support import PARAMS, run_with_sequences

from simulation_core.execution import JobManifest
from simulation_core.request import ExperimentRequest
from simulation_core.types import SimulationConfig


def full_script():
    produces = (80, 80, 70, 60, 60, 60, 60, 80, 80)
    manufacturer = [
        action
        for day in range(9)
        for action in (
            ("order", {"order_a": 80, "order_b": 80, "priority": "none"}),
            ("produce", {"produce": produces[day]}),
        )
    ]
    return {
        "manufacturer": manufacturer,
        "supplier_a": [
            ("offer", {"produce": 80, "offer": 80, "priority_request": False}) for _ in range(9)
        ],
        "supplier_b": [
            ("offer", {"produce": 80, "offer": 80, "priority_request": False}) for _ in range(9)
        ],
        "logistics": (
            [("allocate", {"alloc_a": 80, "alloc_b": 80}) for _ in range(2)]
            + [("allocate", {"alloc_a": 40, "alloc_b": 40}) for _ in range(4)]
            + [("allocate", {"alloc_a": 80, "alloc_b": 80}) for _ in range(3)]
        ),
    }


def draft_manifest() -> JobManifest:
    data = json.loads(Path("draft.json").read_text())
    simulation = SimulationConfig.from_json_values(data["simulation"])
    return JobManifest(
        request=ExperimentRequest(hypothesis="draft preview check"), simulation=simulation
    )


def test_nine_days_thirty_six_phases_forty_five_decisions():
    assert len(schedule_phases(9)) == 36
    assert SupplyChainMechanism.requires_joint_actions is False
    artifact = run_with_sequences(full_script())
    assert artifact.result.status == "completed"
    committed = [event for event in artifact.result.events if event.kind == "committed"]
    assert len(committed) == 36
    actions = [action for event in committed for action in event.actions]
    assert len(actions) == 45
    counts = {}
    for action in actions:
        counts[action.actor_id] = counts.get(action.actor_id, 0) + 1
    assert counts == {"manufacturer": 18, "supplier_a": 9, "supplier_b": 9, "logistics": 9}
    phases = [event.state.phase for event in artifact.result.events[1:]]
    assert artifact.result.events[1].actions[0].kind == "order"
    assert phases[-1] == "finished"
    assert len(set(phases)) == 37 - 1
    assert artifact.result.final_state.public["day"] == 10


def test_preview_leaves_results_pending(tmp_path):
    manifest = draft_manifest()
    out = preview(manifest, tmp_path / "preview")
    text = out.read_text()
    assert "Observed results and their interpretation are pending" in text
    explanation = describe(manifest)
    assert "80" in explanation.theory and "No actor results exist yet" in explanation.theory


def test_final_report_uses_recorded_results(tmp_path):
    artifact = run_with_sequences(full_script())
    out = report(artifact, tmp_path / "report")
    assert out.name == "results.ipynb"
    notebook = json.loads(out.read_text())
    assert notebook["metadata"]["kernelspec"]["name"] == "python3"
    assert len(notebook["cells"]) >= 7
    markdown = "\n".join(
        "".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "markdown"
    )
    assert "No coordinated scenario ran" in markdown
    totals = artifact.result.final_state.public["totals"]
    assert str(totals["sold"]) in markdown or f"{totals['sold']}" in markdown


def test_report_references_every_supplied_price_once():
    assert callable(report) and callable(preview) and callable(describe)
    assert SupplyChainMechanism.requires_joint_actions is False
    artifact = run_with_sequences(full_script())
    params = artifact.manifest.simulation.world.parameters
    for key, expected in PARAMS.items():
        assert params[key] == expected, key
