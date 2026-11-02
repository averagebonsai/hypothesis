"""Reusable notebook generation from a completed job; never re-executes policies."""

import json
from pathlib import Path

from .execution import JobResult


def result_rows(artifact: JobResult) -> dict[str, list[dict[str, object]]]:
    actions: list[dict[str, object]] = [
        {
            "tick": event.state.tick,
            "actor": action.actor_id,
            "kind": action.kind,
            "payload": action.payload,
            "rationale": next((d.rationale for d in event.decisions if d.action == action), None),
        }
        for event in artifact.result.events
        for action in event.actions
    ]
    outcomes: list[dict[str, object]] = [
        {
            "tick": event.state.tick,
            "payoffs": event.outcome.payoffs,
            "metrics": event.outcome.metrics,
        }
        for event in artifact.result.events
        if event.outcome is not None
    ]
    benchmark = artifact.benchmark
    references: list[dict[str, object]] = (
        [
            {
                "index": i,
                "actions": [a.model_dump(mode="json") for a in eq.actions],
                "payoffs": eq.outcome.payoffs,
                "metrics": eq.outcome.metrics,
            }
            for i, eq in enumerate(benchmark.result.equilibria)
        ]
        if benchmark
        else []
    )
    return {"primary_actions": actions, "outcomes": outcomes, "benchmark_solutions": references}


def write_results_notebook(artifact: JobResult, directory: Path) -> Path:
    """An extension may call this helper from its own notebook generator.

    The worker supplies result.json next to the notebook and executes its cells.
    Exported results can contain private data and belong in a restricted directory.
    """
    directory.mkdir(parents=True, exist_ok=True)
    cells: list[dict[str, object]] = []

    def cell(kind: str, source: str) -> None:
        value: dict[str, object] = {
            "cell_type": kind,
            "id": f"cell-{len(cells)}",
            "metadata": {},
            "source": source,
        }
        if kind == "code":
            value.update(execution_count=None, outputs=[])
        cells.append(value)

    cell(
        "markdown",
        "# Experiment results\n\n"
        + artifact.manifest.request.hypothesis
        + "\n\nThis notebook reads the saved job result; rerunning cells does not call actors or models.",
    )
    cell(
        "code",
        "from pathlib import Path\nimport json\nfrom simulation_core.execution import JobResult\nfrom simulation_core.reporting import result_rows\n\nartifact = JobResult.model_validate_json(Path('result.json').read_text())\nrows = result_rows(artifact)\nprint('Run status:', artifact.result.status)\nprint(json.dumps(rows, indent=2))",
    )
    cell(
        "code",
        "import matplotlib.pyplot as plt\n\nobserved = rows['outcomes'][-1]['payoffs'] if rows['outcomes'] else {}\nreference = rows['benchmark_solutions']\nif observed:\n    actors = list(observed)\n    positions = list(range(len(actors)))\n    fig, ax = plt.subplots()\n    ax.bar([x - 0.2 for x in positions], [observed[a] for a in actors], width=0.4, label='Primary payoff')\n    if reference:\n        ax.bar([x + 0.2 for x in positions], [reference[0]['payoffs'].get(a, 0) for a in actors], width=0.4, label='Benchmark 0 payoff')\n    ax.set_xticks(positions, actors)\n    ax.set_ylabel('Payoff')\n    ax.legend()\n    plt.show()\nelse:\n    print('No actor payoffs: see recorded metrics above.')",
    )
    cell(
        "code",
        "print('Assumptions:')\nprint(json.dumps([a.model_dump(mode='json') for a in artifact.result.assumptions], indent=2))\nif artifact.benchmark is not None:\n    print('Benchmark status:', artifact.benchmark.result.status)\n    print('Certification:', artifact.benchmark.result.certification)\n    print('Comparison status:', artifact.benchmark.comparison_status)\n    print('Comparisons:', json.dumps([c.model_dump(mode='json') for c in artifact.benchmark.comparisons], indent=2))\n    print('Applicability:', artifact.benchmark.result.applicability)\nprint('Component IDs:', artifact.result.component_ids)",
    )
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}
        },
        "cells": cells,
    }
    path = directory / "results.ipynb"
    path.write_text(json.dumps(notebook, indent=2, allow_nan=False) + "\n")
    return path
