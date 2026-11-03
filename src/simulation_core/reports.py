"""Explanatory notebooks from recorded results and explicit domain narratives.

This module renders data. Experiments calculate their own mathematical references
outside notebook cells; neither rendering nor reopening a notebook calls policies.
"""

import hashlib
import html
import json
from collections import Counter
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from .execution import JobResult
from .types import Action, Assumption, FrozenModel


def assumption_prose(assumptions: tuple[Assumption, ...]) -> tuple[str, ...]:
    """Use human explanations, never append raw machine configuration values."""
    sources = {
        "user": "user requirement",
        "textbook": "textbook convention",
        "model": "modeling assumption",
        "default": "default assumption",
    }
    return tuple(f"{item.rationale.rstrip('.')} ({sources[item.source]})." for item in assumptions)


SECTIONS = (
    "Experiment background and rationale",
    "Execution and results",
    "Decision rationales",
    "Assumptions",
    "Limitations",
)


class ReportPreview(FrozenModel):
    """Pre-execution content only: deliberately no observed-result/interpretation fields."""

    title: str = Field(min_length=1)
    background: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    theory: str = Field(
        min_length=1,
        description="Calculated benchmark, derivation, applicability; never predicted LLM performance",
    )
    assumptions: tuple[str, ...] = Field(min_length=1)
    limitations: tuple[str, ...] = Field(min_length=1)


def write_preview_notebook(directory: Path, preview: ReportPreview) -> Path:
    """Review problem/theory without inventing actor decisions or interpreting performance."""
    import nbformat  # type: ignore[import-untyped]

    notebook = nbformat.v4.new_notebook(
        metadata={
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "hypothesis_preview": preview.model_dump(mode="json"),
        },
        cells=[
            nbformat.v4.new_markdown_cell(
                f"# {preview.title} — pre-execution preview\n\n## 1. {SECTIONS[0]}\n\n{preview.background}\n\n{preview.rationale}"
            ),
            nbformat.v4.new_markdown_cell(
                f"## 2. Problem definition and theoretical benchmark\n\n{preview.theory}"
            ),
            nbformat.v4.new_code_cell(
                'print("Live execution has not run. Observed results and their interpretation are pending.")'
            ),
            nbformat.v4.new_markdown_cell(
                "## 3. Decision rationales\n\nPending live execution; no actor decisions have been recorded."
            ),
            nbformat.v4.new_markdown_cell(
                "## 4. Assumptions\n\n" + "\n".join(f"- {item}" for item in preview.assumptions)
            ),
            nbformat.v4.new_markdown_cell(
                "## 5. Limitations\n\n" + "\n".join(f"- {item}" for item in preview.limitations)
            ),
        ],
    )
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "preview.ipynb"
    path.write_text(str(nbformat.writes(notebook)))
    return path


def validate_preview_notebook(content: str) -> None:
    notebook = json.loads(content)
    ReportPreview.model_validate_json(json.dumps(notebook["metadata"]["hypothesis_preview"]))
    if "hypothesis_report" in notebook["metadata"]:
        raise ValueError("A preview cannot claim a recorded result")
    text = "\n".join("".join(cell["source"]) for cell in notebook["cells"])
    if "Observed results and their interpretation are pending" not in text:
        raise ValueError("Preview must explicitly leave observed performance pending")


class ReportNarrative(FrozenModel):
    title: str = Field(min_length=1)
    background: str = Field(
        min_length=1,
        description="Explain concepts, participants, rules and information in plain language",
    )
    rationale: str = Field(
        min_length=1, description="Why this experiment and comparison answer the question"
    )
    interpretation: str = Field(
        min_length=1,
        description="Explain the recorded findings, their meaning and scope; do not repeat raw data dumps",
    )
    assumptions: tuple[str, ...] = Field(
        min_length=1,
        description="Readable modeled conditions, with their source where useful; no JSON paths",
    )
    limitations: tuple[str, ...] = Field(min_length=1)


class ReportReference(FrozenModel):
    name: str = Field(min_length=1)
    explanation: str = Field(
        min_length=1, description="Meaning and applicability of the mathematical comparison"
    )
    actions: tuple[Action, ...] = ()
    payoffs: dict[str, float] = Field(default_factory=dict)
    payoff_basis: Literal["round", "cumulative"] = "round"
    source_ticks: dict[str, int] = Field(
        default_factory=dict,
        description="Default: compare each actor's last recorded decision; explicit ticks support trajectories",
    )


class ChartSeries(FrozenModel):
    label: str = Field(min_length=1)
    values: tuple[float, ...]


class ReportMarker(FrozenModel):
    category: str
    label: str
    position: Literal["before", "at"] = "before"


class ReportFigure(FrozenModel):
    title: str = Field(min_length=1)
    ylabel: str = Field(min_length=1)
    categories: tuple[str, ...] = Field(min_length=1)
    series: tuple[ChartSeries, ...] = Field(min_length=1)
    kind: Literal["bar", "line"] = "bar"
    xlabel: str = ""
    markers: tuple[ReportMarker, ...] = ()

    @model_validator(mode="after")
    def dimensions(self) -> Self:
        if any(len(series.values) != len(self.categories) for series in self.series):
            raise ValueError("Every chart series must match its categories")
        if any(marker.category not in self.categories for marker in self.markers):
            raise ValueError("A figure marker must refer to a displayed category")
        return self


class ReportData(FrozenModel):
    narrative: ReportNarrative
    references: tuple[ReportReference, ...] = ()
    figures: tuple[ReportFigure, ...] = ()
    result_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


def result_digest(artifact: JobResult) -> str:
    return hashlib.sha256(artifact.model_dump_json().encode()).hexdigest()


def write_experiment_notebook(
    artifact: JobResult,
    directory: Path,
    narrative: ReportNarrative,
    *,
    references: tuple[ReportReference, ...] = (),
    figures: tuple[ReportFigure, ...] = (),
) -> Path:
    """Five-section report; recorded decisions and explanations have one display each.

    Domain code supplies narrative and calculated references/figures. Metadata
    binds these to the authoritative result, keeping the exported notebook/result
    pair self-contained. Cells call shared external rendering functions only.
    """
    actors = {actor.id for actor in artifact.manifest.simulation.world.actors}
    decisions = {
        (event.state.tick, action.actor_id)
        for event in artifact.result.events
        for action in event.actions
    }
    for reference in references:
        ids = [action.actor_id for action in reference.actions]
        if (
            len(set(ids)) != len(ids)
            or (set(ids) | set(reference.payoffs) | set(reference.source_ticks)) - actors
        ):
            raise ValueError("Reference has duplicate or unknown actors")
        if any((tick, actor) not in decisions for actor, tick in reference.source_ticks.items()):
            raise ValueError("Reference tick does not identify a recorded actor decision")
    report = ReportData(
        narrative=narrative,
        references=references,
        figures=figures,
        result_sha256=result_digest(artifact),
    )
    cells: list[dict[str, object]] = []

    def cell(kind: str, source: str, tag: str = "") -> None:
        value: dict[str, object] = {
            "cell_type": kind,
            "id": f"report-{len(cells)}",
            "source": source,
            "metadata": {"tags": [tag]} if tag else {},
        }
        if kind == "code":
            value.update(execution_count=None, outputs=[])
        cells.append(value)

    cell(
        "markdown",
        f"# {narrative.title}\n\n## 1. {SECTIONS[0]}\n\n{narrative.background}\n\n{narrative.rationale}",
    )
    cell(
        "markdown",
        f"## 2. {SECTIONS[1]}\n\nThe code below loads this recorded run. Reopening or rerunning these reporting cells makes no model calls and does not repeat the simulation.",
    )
    cell(
        "code",
        "from simulation_core.reports import load_report, display_results, plot_figure, display_decision_rationales\n\nartifact, report = load_report()\ndisplay_results(artifact, report.references)",
        "report_results",
    )
    for index in range(len(figures)):
        cell("code", f"plot_figure(report.figures[{index}])", "report_figure")
    comparison = "\n\n".join(f"**{ref.name}:** {ref.explanation}" for ref in references)
    cell("markdown", narrative.interpretation + ("\n\n" + comparison if comparison else ""))
    cell(
        "markdown",
        f"## 3. {SECTIONS[2]}\n\nThese are the explanations recorded with each actor's decision. They describe what the actor reported; they do not independently prove why it behaved that way.",
    )
    cell("code", "display_decision_rationales(artifact)", "report_rationales")
    cell(
        "markdown",
        f"## 4. {SECTIONS[3]}\n\n" + "\n".join(f"- {text}" for text in narrative.assumptions),
    )
    cell(
        "markdown",
        f"## 5. {SECTIONS[4]}\n\n" + "\n".join(f"- {text}" for text in narrative.limitations),
    )
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "results.ipynb"
    path.write_text(
        json.dumps(
            {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {
                    "kernelspec": {
                        "display_name": "Python 3",
                        "language": "python",
                        "name": "python3",
                    },
                    "hypothesis_report": report.model_dump(mode="json"),
                },
                "cells": cells,
            },
            indent=2,
        )
        + "\n"
    )
    return path


def load_report(directory: Path = Path(".")) -> tuple[JobResult, ReportData]:
    artifact = JobResult.model_validate_json((directory / "result.json").read_text())
    notebook = json.loads((directory / "results.ipynb").read_text())
    report = ReportData.model_validate_json(json.dumps(notebook["metadata"]["hypothesis_report"]))
    if result_digest(artifact) != report.result_sha256:
        raise ValueError("Report metadata belongs to a different recorded result")
    return artifact, report


def _value(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, dict):
        return "; ".join(f"{k}: {_value(v)}" for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return ", ".join(_value(v) for v in value)
    return str(value)


def display_results(artifact: JobResult, references: tuple[ReportReference, ...] = ()) -> None:
    from IPython.display import HTML, display  # type: ignore[import-untyped]

    events = [event for event in artifact.result.events if event.actions]
    last_ticks = {action.actor_id: event.state.tick for event in events for action in event.actions}
    headers = ["Turn", "Actor", "Action", "Payoff"]
    show_cumulative = any(reference.payoff_basis == "cumulative" for reference in references)
    if show_cumulative:
        headers.append("Cumulative payoff")
    for reference in references:
        metric = "cumulative payoff" if reference.payoff_basis == "cumulative" else "payoff"
        headers += [
            f"{reference.name}: action",
            f"{reference.name}: {metric}",
            f"{metric.capitalize()} difference",
        ]
    rows = []
    cumulative: dict[str, float] = {}
    for event in events:
        if event.outcome:
            for actor_id, value in event.outcome.payoffs.items():
                cumulative[actor_id] = cumulative.get(actor_id, 0.0) + value
        for action in event.actions:
            payoff = event.outcome.payoffs.get(action.actor_id) if event.outcome else None
            row: list[object] = [event.state.tick, action.actor_id, _value(action.payload), payoff]
            if show_cumulative:
                row.append(cumulative.get(action.actor_id))
            for reference in references:
                applies = event.state.tick == reference.source_ticks.get(
                    action.actor_id, last_ticks[action.actor_id]
                )
                ref_action = (
                    next((a for a in reference.actions if a.actor_id == action.actor_id), None)
                    if applies
                    else None
                )
                ref_payoff = reference.payoffs.get(action.actor_id) if applies else None
                observed = (
                    cumulative.get(action.actor_id)
                    if reference.payoff_basis == "cumulative"
                    else payoff
                )
                row += [
                    _value(ref_action.payload) if ref_action else None,
                    ref_payoff,
                    observed - ref_payoff
                    if observed is not None and ref_payoff is not None
                    else None,
                ]
            rows.append(row)
    table = (
        "<table><thead><tr>"
        + "".join(f"<th>{html.escape(h)}</th>" for h in headers)
        + "</tr></thead><tbody>"
    )
    table += "".join(
        "<tr>" + "".join(f"<td>{html.escape(_value(v))}</td>" for v in row) + "</tr>"
        for row in rows
    )
    display(HTML(table + "</tbody></table>"))


def display_decision_rationales(artifact: JobResult) -> None:
    from IPython.display import Markdown, display  # type: ignore[import-untyped]

    lines = [
        f"**{decision.action.actor_id}, turn {event.state.tick}:** {decision.rationale or 'No explanation was recorded.'}"
        for event in artifact.result.events
        for decision in event.decisions
    ]
    display(Markdown("\n\n".join(lines) or "No actor decisions were recorded."))


def plot_figure(figure: ReportFigure) -> None:
    import matplotlib.pyplot as plt

    _, ax = plt.subplots(figsize=(8, 4))
    width = 0.8 / len(figure.series)
    for index, series in enumerate(figure.series):
        positions = [x - 0.4 + width * (index + 0.5) for x in range(len(figure.categories))]
        if figure.kind == "line":
            ax.plot(range(len(figure.categories)), series.values, marker="o", label=series.label)
        else:
            ax.bar(positions, series.values, width=width, label=series.label)
    for marker in figure.markers:
        position = figure.categories.index(marker.category) - (
            0.5 if marker.position == "before" else 0
        )
        ax.axvline(position, color="black", linestyle="--", label=marker.label)
    ax.set_xticks(range(len(figure.categories)), figure.categories)
    ax.set_title(figure.title)
    ax.set_ylabel(figure.ylabel)
    ax.set_xlabel(figure.xlabel)
    ax.legend()
    plt.tight_layout()
    plt.show()


def validate_explanatory_notebook(
    content: str, artifact: JobResult, *, executed: bool = False
) -> None:
    """Structural/data checks, not an automated claim of explanatory quality."""
    notebook = json.loads(content)
    cells = notebook["cells"]
    source = lambda c: "".join(c["source"]) if isinstance(c["source"], list) else c["source"]
    markdown = "\n".join(source(c) for c in cells if c["cell_type"] == "markdown")
    headings = [f"## {i}. {title}" for i, title in enumerate(SECTIONS, 1)]
    positions = [markdown.find(h) for h in headings]
    if any(markdown.count(h) != 1 for h in headings) or positions != sorted(positions):
        raise ValueError("Notebook must contain the five ordered explanatory sections exactly once")
    if "```json" in markdown.lower():
        raise ValueError("Explain assumptions and results in normal prose, not JSON dumps")
    for tag in ("report_results", "report_rationales"):
        if sum(tag in c.get("metadata", {}).get("tags", []) for c in cells) != 1:
            raise ValueError("Recorded results and rationales must each have one display cell")
    section = 0
    for cell in cells:
        if cell["cell_type"] == "markdown":
            for index, heading in enumerate(headings, 1):
                if heading in source(cell):
                    section = index
        tags = cell.get("metadata", {}).get("tags", [])
        if ("report_results" in tags and section != 2) or (
            "report_rationales" in tags and section != 3
        ):
            raise ValueError("Results and rationales must be displayed in their own sections")
    report = ReportData.model_validate_json(json.dumps(notebook["metadata"]["hypothesis_report"]))
    if report.result_sha256 != result_digest(artifact):
        raise ValueError("Report refers to a different recorded result")
    if executed:
        text = markdown
        for cell in cells:
            for output in cell.get("outputs", []):
                data = output.get("data", {})
                value = data.get(
                    "text/markdown",
                    data.get("text/html", data.get("text/plain", output.get("text", ""))),
                )
                text += "\n" + ("".join(value) if isinstance(value, list) else value)
        rationales = Counter(
            f"**{d.action.actor_id}, turn {e.state.tick}:** {d.rationale or 'No explanation was recorded.'}"
            for e in artifact.result.events
            for d in e.decisions
        )
        if any(text.count(block) != count for block, count in rationales.items()):
            raise ValueError(
                "Recorded decision explanations must appear once per decision, only in their section"
            )
