"""Notebook schema checks and data-only host export; never execute notebook code here."""

import json
import os
from pathlib import Path

from .specs import DiagnosticArtifact, WorkerResponse


def export_notebook(response: WorkerResponse, directory: Path) -> None:
    if response.notebook_json is None or response.result is None:
        raise ValueError("No completed notebook/result pair to export")
    directory.mkdir(mode=0o700)
    for name, content in (
        ("results.ipynb", response.notebook_json),
        ("result.json", response.result.model_dump_json(indent=2)),
    ):
        descriptor = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(content + "\n")


def validate_notebook_json(content: str) -> None:
    # Schema validation is data-only; kernels execute exclusively in the worker.
    import nbformat  # type: ignore[import-untyped]

    notebook = nbformat.reads(content, as_version=4)
    nbformat.validate(notebook)
    if not any(cell.cell_type == "code" for cell in notebook.cells):
        raise ValueError("A results notebook must contain executable reporting cells")
    if any(
        output.output_type == "error"
        for cell in notebook.cells
        if cell.cell_type == "code"
        for output in cell.outputs
    ):
        raise ValueError("Notebook contains execution errors")
    json.loads(content)


def export_diagnostic(artifact: DiagnosticArtifact, directory: Path) -> None:
    """Export retained failed-run evidence, explicitly separate from approved results."""
    directory.mkdir(mode=0o700, parents=True)
    documents = {
        "UNAPPROVED.json": json.dumps(
            {
                "status": artifact.status,
                "findings": [finding.model_dump(mode="json") for finding in artifact.findings],
            },
            indent=2,
        ),
        "result.json": artifact.result.model_dump_json(indent=2),
    }
    if artifact.notebook is not None:
        content = json.dumps(artifact.notebook, indent=2, allow_nan=False)
        validate_notebook_json(content)
        documents["results.ipynb"] = content
    for name, content in documents.items():
        descriptor = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(content + "\n")
