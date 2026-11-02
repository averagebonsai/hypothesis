"""Generate and execute extension notebooks exclusively inside the isolated worker."""

import importlib
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_tools.notebooks import validate_notebook_json
from agent_tools.specs import NotebookSpec
from simulation_core.execution import JobResult


def execute_report(artifact: JobResult, specification: NotebookSpec) -> str:
    import nbformat  # type: ignore[import-untyped]
    from nbclient import NotebookClient

    from .runtime import require_container

    require_container()
    module, symbol = specification.generator.split(":")
    generator = getattr(importlib.import_module(module), symbol)
    with TemporaryDirectory(prefix="experiment-report-") as temporary:
        directory = Path(temporary)
        data = artifact.model_dump_json(indent=2)
        (directory / "result.json").write_text(data)
        path = generator(artifact.model_copy(deep=True), directory)
        if (
            not isinstance(path, Path)
            or path.is_symlink()
            or path.resolve() != directory / "results.ipynb"
        ):
            raise ValueError("Notebook generator must return output_directory/results.ipynb")
        if path.stat().st_size > 2_000_000:
            raise ValueError("Generated notebook exceeds the report size limit")
        validate_notebook_json(path.read_text())
        notebook = nbformat.reads(path.read_text(), as_version=4)
        NotebookClient(
            notebook,
            timeout=60,
            kernel_name="python3",
            allow_errors=False,
            resources={"metadata": {"path": str(directory)}},
        ).execute()
        if (directory / "result.json").read_text() != data:
            raise ValueError("Report modified its authoritative result data")
        content = str(nbformat.writes(notebook))
        if len(content.encode()) > 2_000_000:
            raise ValueError("Executed notebook exceeds the report size limit")
        validate_notebook_json(content)
        if not all(
            cell.execution_count is not None for cell in notebook.cells if cell.cell_type == "code"
        ):
            raise ValueError("Notebook code cells were not executed")
        return content
