"""Keep completed intermediate artifacts without granting acceptance."""

import json
from pathlib import Path

from agent_tools.specs import DiagnosticArtifact, VerificationFinding
from simulation_core.execution import JobResult

DIRECTORY = Path("/tmp/hypothesis-unapproved-diagnostic")


def record(
    artifact: JobResult, findings: tuple[VerificationFinding, ...] = (), notebook: str | None = None
) -> None:
    DIRECTORY.mkdir(mode=0o700, exist_ok=True)
    (DIRECTORY / "result.json").write_text(artifact.model_dump_json())
    (DIRECTORY / "findings.json").write_text(
        json.dumps([finding.model_dump(mode="json") for finding in findings])
    )
    if notebook is not None:
        (DIRECTORY / "results.ipynb").write_text(notebook)


def read() -> DiagnosticArtifact | None:
    path = DIRECTORY / "result.json"
    if not path.exists():
        return None
    for candidate in DIRECTORY.iterdir():
        if (
            candidate.is_symlink()
            or not candidate.is_file()
            or candidate.stat().st_size > 2_000_000
        ):
            raise ValueError("Invalid diagnostic artifact")
    artifact = JobResult.model_validate_json(path.read_text())
    notebook = DIRECTORY / "results.ipynb"
    findings = DIRECTORY / "findings.json"
    return DiagnosticArtifact(
        result=artifact,
        notebook=json.loads(notebook.read_text()) if notebook.exists() else None,
        findings=tuple(
            VerificationFinding.model_validate_json(json.dumps(value))
            for value in json.loads(findings.read_text())
        )
        if findings.exists()
        else (),
    )
