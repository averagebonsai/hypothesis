"""Generate and execute extension notebooks exclusively inside the isolated worker."""

import contextlib
import importlib
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_tools.notebooks import validate_notebook_json
from agent_tools.specs import NotebookSpec
from simulation_core.execution import JobManifest, JobResult


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
        if specification.report_version == "explanatory.v1":
            from simulation_core.reports import validate_explanatory_notebook

            validate_explanatory_notebook(path.read_text(), artifact)
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
        if specification.report_version == "explanatory.v1":
            validate_explanatory_notebook(content, artifact, executed=True)
        if not all(
            cell.execution_count is not None for cell in notebook.cells if cell.cell_type == "code"
        ):
            raise ValueError("Notebook code cells were not executed")
        return content


def execute_preview(job: JobManifest, specification: NotebookSpec) -> str:
    import nbformat  # type: ignore[import-untyped]
    from nbclient import NotebookClient

    from simulation_core.reports import validate_preview_notebook

    from .runtime import require_container

    require_container()
    if specification.preview_generator is None:
        raise ValueError("This bundle does not declare a preview generator")
    module, symbol = specification.preview_generator.split(":")
    generator = getattr(importlib.import_module(module), symbol)
    with TemporaryDirectory(prefix="experiment-preview-") as temporary:
        directory = Path(temporary)
        path = generator(job.model_copy(deep=True), directory)
        if (
            not isinstance(path, Path)
            or path.is_symlink()
            or path.resolve() != directory / "preview.ipynb"
        ):
            raise ValueError("Preview generator must return output_directory/preview.ipynb")
        if path.stat().st_size > 2_000_000:
            raise ValueError("Preview exceeds size limit")
        content = path.read_text()
        validate_notebook_json(content)
        validate_preview_notebook(content)
        notebook = nbformat.reads(content, as_version=4)
        NotebookClient(
            notebook,
            timeout=60,
            kernel_name="python3",
            allow_errors=False,
            resources={"metadata": {"path": str(directory)}},
        ).execute()
        content = str(nbformat.writes(notebook))
        if len(content.encode()) > 2_000_000:
            raise ValueError("Executed preview exceeds size limit")
        validate_notebook_json(content)
        validate_preview_notebook(content)
        return content


def main() -> None:
    """Separate offline entry point; never serves an actor relay or runs a simulation."""
    from agent_tools.bundles import verify_bundle
    from agent_tools.specs import CheckResult, ReportResponse, VerificationFinding

    from .runtime import _check, load_registry, require_container
    from .verification import assess

    require_container()
    if len(sys.argv) != 3 or sys.argv[1] not in {"preview", "report"}:
        raise SystemExit("Usage: extension_worker.reporting {preview|report} BUNDLE_DIGEST")
    mode, digest = sys.argv[1:]
    try:
        with contextlib.redirect_stdout(sys.stderr):
            root = Path("/bundle")
            manifest, seal, _ = verify_bundle(root, check_location=False)
            if seal.digest != digest or manifest.notebook is None:
                raise ValueError("Sealed reporting bundle/specification mismatch")
            _, registry = load_registry(root)
            findings: tuple[VerificationFinding, ...] = ()
            checks: tuple[CheckResult, ...] = ()
            if mode == "preview":
                job = JobManifest.model_validate_json(Path("/job/manifest.json").read_text())
                content = execute_preview(job, manifest.notebook)
            else:
                with TemporaryDirectory(prefix="report-checks-") as temporary:
                    checks = tuple(
                        _check(name, args)
                        for name, args in (
                            (
                                "ruff",
                                [
                                    "ruff",
                                    "check",
                                    "--no-cache",
                                    "--config",
                                    "/opt/toolkit/pyproject.toml",
                                    "/bundle/experiment_extension",
                                    "/bundle/tests",
                                ],
                            ),
                            (
                                "mypy",
                                [
                                    "mypy",
                                    "--config-file",
                                    "/opt/toolkit/pyproject.toml",
                                    "--cache-dir",
                                    temporary + "/mypy",
                                    "/bundle/experiment_extension",
                                ],
                            ),
                            (
                                "acceptance",
                                [
                                    sys.executable,
                                    "-m",
                                    "pytest",
                                    "-q",
                                    "-p",
                                    "no:cacheprovider",
                                    "-c",
                                    "/opt/toolkit/docker/pytest.ini",
                                    "/bundle/tests",
                                ],
                            ),
                        )
                    )
                if not all(check.passed for check in checks):
                    print(
                        ReportResponse(
                            bundle_digest=digest,
                            checks=checks,
                            error="Report source validation failed",
                        ).model_dump_json(),
                        file=sys.__stdout__,
                    )
                    return
                artifact = JobResult.model_validate_json(Path("/job/result.json").read_text())
                configured = JobManifest.model_validate_json(
                    (root / "job.example.json").read_text()
                )
                if artifact.manifest != configured:
                    raise ValueError("Saved result does not match bundle's scientific job")
                findings = assess(artifact, manifest, registry)
                if any(f.required and f.status != "verified" for f in findings):
                    raise ValueError("Saved result failed required verification")
                content = execute_report(artifact, manifest.notebook)
            response = ReportResponse(
                bundle_digest=digest,
                notebook_json=content,
                verification_findings=findings,
                checks=checks,
            )
    except Exception as exc:  # noqa: BLE001 - isolated process boundary
        response = ReportResponse(
            bundle_digest=digest, error=f"{type(exc).__name__}: {str(exc)[:2000]}"
        )
    print(response.model_dump_json())


if __name__ == "__main__":
    main()
