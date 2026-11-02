from pathlib import Path

from simulation_core.execution import JobResult
from simulation_core.reporting import write_results_notebook


def generate(artifact: JobResult, output_directory: Path) -> Path:
    path = write_results_notebook(artifact, output_directory)
    text = path.read_text()
    text = text.replace(
        "This notebook reads the saved job result;",
        "Primary action is the scripted fixture; the solver is a separate analytic benchmark.\n\nThis notebook reads the saved job result;",
    )
    path.write_text(text)
    return path
