import json
from pathlib import Path

from simulation_core.execution import JobResult
from simulation_core.reporting import write_results_notebook


def generate(artifact: JobResult, output_directory: Path) -> Path:
    path = write_results_notebook(artifact, output_directory)
    notebook = json.loads(path.read_text())
    intro = (
        "Primary action is the scripted fixture; the solver is a separate analytic benchmark.\n\n"
        + str(notebook["cells"][0]["source"])
    )
    notebook["cells"][0]["source"] = intro
    path.write_text(json.dumps(notebook, indent=2, allow_nan=False) + "\n")
    return path
