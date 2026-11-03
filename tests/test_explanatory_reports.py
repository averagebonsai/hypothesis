"""Report structure, data binding and notebook execution without live model calls."""

import json
import os
from pathlib import Path

import pytest

from simulation_core.reports import (
    ChartSeries,
    ReportFigure,
    ReportNarrative,
    ReportReference,
    load_report,
    validate_explanatory_notebook,
    write_experiment_notebook,
)


def narrative():
    return ReportNarrative(
        title="A recorded decision experiment",
        background="An actor chooses a number. Its payoff measures the benefit or cost of the recorded choice.",
        rationale="Compare the observed decision with a separately calculated reference to understand the gap.",
        interpretation="The observed payoff is below the reference. This example illustrates a difference, without establishing behavior across repeated trials.",
        assumptions=(
            "User supplied: the reference and observed decisions use the same outcome units.",
        ),
        limitations=("One recorded observation cannot establish a population-level conclusion.",),
    )


def write(artifact, tmp_path):
    (tmp_path / "result.json").write_text(artifact.model_dump_json())
    return write_experiment_notebook(
        artifact,
        tmp_path,
        narrative(),
        references=(
            ReportReference(
                name="Reference",
                explanation="A separately calculated comparison, not an actor decision.",
                actions=artifact.benchmark.result.equilibria[0].actions,
                payoffs=artifact.benchmark.result.equilibria[0].outcome.payoffs,
            ),
        ),
        figures=(
            ReportFigure(
                title="Outcome comparison",
                ylabel="Payoff",
                categories=("actor",),
                series=(
                    ChartSeries(label="Observed", values=(-4.0,)),
                    ChartSeries(label="Reference", values=(0.0,)),
                ),
            ),
        ),
    )


def test_five_sections_and_self_contained_data_binding(artifact, tmp_path):
    path = write(artifact, tmp_path)
    validate_explanatory_notebook(path.read_text(), artifact)
    restored, report = load_report(tmp_path)
    assert restored == artifact and report.references[0].payoffs == {"worker": 0.0}
    document = json.loads(path.read_text())
    source = "\n".join(c["source"] for c in document["cells"])
    assert "```json" not in source
    assert "json.dumps(rows" not in source
    assert "display_decision_rationales(artifact)" in source
    assert all("truthful" not in c["source"] for c in document["cells"] if c["cell_type"] == "code")
    (tmp_path / "result.json").write_text(
        artifact.model_copy(update={"benchmark": None}).model_dump_json()
    )
    with pytest.raises(ValueError, match="different recorded result"):
        load_report(tmp_path)


def test_duplicate_displays_and_raw_json_are_rejected(artifact, tmp_path):
    path = write(artifact, tmp_path)
    data = json.loads(path.read_text())
    data["cells"].append(
        next(c for c in data["cells"] if "report_rationales" in c["metadata"].get("tags", []))
    )
    with pytest.raises(ValueError, match="one display"):
        validate_explanatory_notebook(json.dumps(data), artifact)
    data = json.loads(path.read_text())
    data["cells"][-2]["source"] += "\n```json\n{}\n```"
    with pytest.raises(ValueError, match="normal prose"):
        validate_explanatory_notebook(json.dumps(data), artifact)


def test_unknown_actor_reference_and_chart_dimensions_rejected(artifact, tmp_path):
    with pytest.raises(ValueError, match="unknown actors"):
        write_experiment_notebook(
            artifact,
            tmp_path,
            narrative(),
            references=(
                ReportReference(name="Bad", explanation="wrong actor", payoffs={"unknown": 1.0}),
            ),
        )
    with pytest.raises(ValueError, match="categories"):
        ReportFigure(
            title="Bad",
            ylabel="Amount",
            categories=("one", "two"),
            series=(ChartSeries(label="one", values=(1.0,)),),
        )


@pytest.mark.skipif(
    not Path("/.dockerenv").exists() or os.geteuid() != 10001,
    reason="Notebook kernels execute in the isolated worker",
)
def test_explanatory_notebook_executes_external_helpers(artifact, tmp_path):
    import nbformat
    from nbclient import NotebookClient

    path = write(artifact, tmp_path)
    notebook = nbformat.reads(path.read_text(), as_version=4)
    NotebookClient(
        notebook, timeout=60, kernel_name="python3", resources={"metadata": {"path": str(tmp_path)}}
    ).execute()
    validate_explanatory_notebook(nbformat.writes(notebook), artifact, executed=True)
    assert all(c.execution_count is not None for c in notebook.cells if c.cell_type == "code")


def test_executed_rationales_are_once_per_actor_turn_not_substring_matches(tmp_path):
    from examples.llm_payoff_matrix import fake_response, run_llm_job
    from simulation_core.model_gateway import FakeGateway

    artifact = run_llm_job(gateway=FakeGateway(fake_response), rounds=2)
    path = write_experiment_notebook(artifact, tmp_path, narrative())
    data = json.loads(path.read_text())
    cell = next(c for c in data["cells"] if "report_rationales" in c["metadata"].get("tags", []))
    text = "\n\n".join(
        f"**{d.action.actor_id}, turn {e.state.tick}:** {d.rationale}"
        for e in artifact.result.events
        for d in e.decisions
    )
    cell["outputs"] = [
        {"output_type": "display_data", "data": {"text/markdown": text}, "metadata": {}}
    ]
    validate_explanatory_notebook(json.dumps(data), artifact, executed=True)
    cell["outputs"].append(cell["outputs"][0])
    with pytest.raises(ValueError, match="once per decision"):
        validate_explanatory_notebook(json.dumps(data), artifact, executed=True)


def test_cumulative_reference_compares_like_units_instead_of_last_round(artifact, monkeypatch):
    from simulation_core.reports import display_results
    from simulation_core.types import Action, Event, Outcome

    actor = artifact.manifest.simulation.world.actors[0].id
    initialized = Event(
        sequence=0,
        kind="initialized",
        state=artifact.result.final_state.model_copy(update={"tick": 0}),
    )
    original = Event(
        sequence=1,
        kind="committed",
        state=initialized.state.model_copy(update={"tick": 1}),
        actions=(Action(actor_id=actor, kind="submit", payload={"value": 1.0}),),
        outcome=Outcome(payoffs={actor: 2.0}),
    )
    first = original
    second = original.model_copy(
        update={
            "sequence": 2,
            "state": original.state.model_copy(update={"tick": 2}),
            "outcome": Outcome(payoffs={actor: 3.0}),
        }
    )
    data = artifact.model_copy(
        update={
            "result": artifact.result.model_copy(update={"events": (initialized, first, second)})
        }
    )
    outputs = []
    monkeypatch.setattr("IPython.display.display", outputs.append)
    display_results(
        data,
        (
            ReportReference(
                name="Total reference",
                explanation="Cumulative total",
                payoffs={actor: 4.0},
                payoff_basis="cumulative",
            ),
        ),
    )
    html = outputs[0].data
    assert "Cumulative payoff" in html
    # Final row: round payoff 3, cumulative payoff 5, reference 4, difference +1.
    assert "<td>3</td><td>5</td><td>—</td><td>4</td><td>1</td>" in html
