"""Container-only experimental imports and validation; no host execution fallback."""

import contextlib
import importlib
import importlib.metadata
import inspect
import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import cast, get_args

from pydantic import BaseModel, JsonValue, TypeAdapter

from agent_tools.bundles import verify_bundle
from agent_tools.jobs import ToolJobManifest
from agent_tools.process import bounded_command
from agent_tools.specs import BundleManifest, CheckResult, PythonDistribution, WorkerResponse
from agent_tools.verification import verify_problem_result
from components.library import standard_registry
from simulation_core.execution import JobManifest, JobRunner, LocalBackend
from simulation_core.mechanism import Mechanism
from simulation_core.policy import Policy
from simulation_core.protocol import ProtocolRules
from simulation_core.registry import ComponentRegistry
from simulation_core.solver import GameView, Solver

from .diagnostics import read as read_diagnostic
from .verification import assess

APPROVED_DEPENDENCIES = frozenset(get_args(PythonDistribution))
PARENTS = {
    "policy": Policy,
    "mechanism": Mechanism,
    "protocol": ProtocolRules,
    "solver": Solver,
    "game_view": GameView,
    "action_schema": BaseModel,
    "parameter_schema": BaseModel,
}
TABLES = {
    "policy": "policies",
    "mechanism": "mechanisms",
    "protocol": "protocols",
    "solver": "solvers",
    "game_view": "game_views",
    "action_schema": "action_schemas",
    "parameter_schema": "parameter_schemas",
}


def require_container() -> None:
    if not Path("/.dockerenv").is_file() or os.geteuid() != 10001:
        raise RuntimeError(
            "Experimental imports are permitted only in the restricted worker container"
        )


def load_registry(root: Path) -> tuple[BundleManifest, ComponentRegistry]:
    require_container()
    manifest, _, _ = verify_bundle(root, check_location=False)
    for dependency in manifest.existing_dependencies:
        if dependency not in APPROVED_DEPENDENCIES:
            raise ValueError(
                f"Dependency requires approval and a new trusted lock/image: {dependency}"
            )
        importlib.metadata.version(dependency)
    registry = standard_registry()
    # Trusted core imports above precede the experimental import path.
    sys.path.append(str(root))
    for component in manifest.components:
        module_name, name = component.symbol.split(":")
        exported = getattr(importlib.import_module(module_name), name)
        if component.kind == "utility":
            if not callable(exported):
                raise TypeError("Utility export must be callable")
            continue
        parent = PARENTS[component.kind]
        if (
            not isinstance(exported, type)
            or not issubclass(exported, parent)
            or inspect.isabstract(exported)
        ):
            raise TypeError(f"{component.id} does not implement {component.parent_interface}")
        if (
            component.kind == "solver"
            and cast(type[Solver], exported).contract != component.method_contract
        ):
            raise ValueError("Solver implementation and specified method contract disagree")
        table = getattr(registry, TABLES[component.kind])
        if component.id in table:
            raise ValueError("Experimental exports cannot replace approved components")
        table[component.id] = exported
    return manifest, registry


def resolved_schemas(
    manifest: BundleManifest, registry: ComponentRegistry
) -> dict[str, dict[str, JsonValue]]:
    """Derive model contracts from actual exported classes, not descriptive strings."""
    schemas = {
        "action:" + key: model.model_json_schema() for key, model in registry.action_schemas.items()
    }
    schemas.update(
        {
            "parameter:" + key: model.model_json_schema()
            for key, model in registry.parameter_schemas.items()
        }
    )
    for component in manifest.components:
        for direction, reference in (
            ("input", component.input_model),
            ("output", component.output_model),
        ):
            if reference is None:
                continue
            module, symbol = reference.split(":")
            model = getattr(importlib.import_module(module), symbol)
            if not isinstance(model, type) or not issubclass(model, BaseModel):
                raise TypeError("Schema references must resolve to Pydantic classes")
            schemas[component.id + ":" + direction] = model.model_json_schema()
    return schemas


def _check(name: str, command: list[str], *, seconds: int = 90) -> CheckResult:
    result = bounded_command(command, seconds=seconds, max_bytes=300_000)
    return CheckResult(
        name=name,
        passed=result.code == 0,
        exit_code=result.code,
        output=(result.stdout + result.stderr)[-100_000:],
    )


def execute(operation: str, expected_digest: str) -> WorkerResponse:
    require_container()
    root = Path("/bundle")
    manifest, seal, _ = verify_bundle(root, check_location=False)
    if seal.digest != expected_digest:
        raise ValueError("Staged bundle digest differs from the requested digest")
    job = TypeAdapter(JobManifest | ToolJobManifest).validate_json(
        Path("/job/manifest.json").read_text()
    )
    checks = []
    with tempfile.TemporaryDirectory(prefix="extension-validation-") as temporary:
        xml_path = Path(temporary) / "acceptance.xml"
        commands = [
            (
                "ruff",
                [
                    "ruff",
                    "check",
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
                    "-c",
                    "/opt/toolkit/docker/pytest.ini",
                    "--junitxml",
                    str(xml_path),
                    "/bundle/tests",
                    "/opt/toolkit/docker/tool_contract_tests.py"
                    if isinstance(job, ToolJobManifest)
                    else "/opt/toolkit/docker/contract_tests.py",
                ],
            ),
            (
                "regressions",
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "-c",
                    "/opt/toolkit/docker/pytest.ini",
                    "/opt/toolkit/tests",
                ],
            ),
        ]
        for name, command in commands:
            check = _check(name, command)
            checks.append(check)
        if not all(check.passed for check in checks):
            return WorkerResponse(
                bundle_digest=seal.digest, checks=tuple(checks), diagnostic=read_diagnostic()
            )
        names = {
            test.attrib.get("name", "").split("[")[0]
            for test in ET.parse(xml_path).iter("testcase")
            if test.find("skipped") is None
        }
        required = {
            test.name for component in manifest.components for test in component.acceptance_tests
        }
        missing = sorted(required - names)
        checks.append(
            CheckResult(
                name="declared_acceptance",
                passed=not missing,
                exit_code=1 if missing else 0,
                output="Missing executed tests: " + ", ".join(missing)
                if missing
                else "All declared tests executed",
            )
        )
        if missing:
            return WorkerResponse(bundle_digest=seal.digest, checks=tuple(checks))
    # Imports/registration and even validation stay inside the container.
    _, registry = load_registry(root)
    schemas = resolved_schemas(manifest, registry)
    if isinstance(job, ToolJobManifest):
        from .tools import execute_tool

        checks.append(
            CheckResult(
                name="composition",
                passed=True,
                exit_code=0,
                output="Namespaced callable/schema exports loaded; no simulation scaffold",
            )
        )
        return WorkerResponse(
            bundle_digest=seal.digest,
            checks=tuple(checks),
            tool_result=execute_tool(job, manifest) if operation == "run" else None,
            resolved_schemas=schemas,
        )
    registry.validate_config(job.simulation)
    checks.append(
        CheckResult(
            name="composition",
            passed=True,
            exit_code=0,
            output="Job-local registry passed preflight",
        )
    )
    if operation == "validate":
        return WorkerResponse(
            bundle_digest=seal.digest, checks=tuple(checks), resolved_schemas=schemas
        )
    artifact = JobRunner(LocalBackend(registry)).run(job.request, job.simulation)
    findings = assess(artifact, manifest, registry)
    if any(finding.required and finding.status != "verified" for finding in findings):
        from .diagnostics import record

        record(artifact, findings)
        return WorkerResponse(
            bundle_digest=seal.digest,
            checks=tuple(checks),
            verification_findings=findings,
            diagnostic=read_diagnostic(),
        )
    notebook_json = None
    if manifest.notebook is not None:
        from .reporting import execute_report

        notebook_json = execute_report(artifact, manifest.notebook)
    probe_results = []
    probes_path = Path("/job/probes.json")
    if probes_path.exists():
        for value in json.loads(probes_path.read_text()):
            probe = JobManifest.model_validate(value)
            _, fresh_registry = load_registry(root)
            probe_artifact = JobRunner(LocalBackend(fresh_registry)).run(
                probe.request, probe.simulation
            )
            verify_problem_result(probe_artifact, manifest.verification)
            probe_results.append(probe_artifact)
    return WorkerResponse(
        bundle_digest=seal.digest,
        checks=tuple(checks),
        result=artifact,
        probe_results=tuple(probe_results),
        notebook_json=notebook_json,
        verification_findings=findings,
        resolved_schemas=schemas,
    )


def main() -> None:
    if len(sys.argv) != 3 or sys.argv[1] not in {"validate", "run"}:
        raise SystemExit("Usage: extension_worker {validate|run} BUNDLE_DIGEST")
    require_container()
    # Ordinary experimental print output cannot contaminate the structured response.
    try:
        with contextlib.redirect_stdout(sys.stderr):
            response = execute(sys.argv[1], sys.argv[2])
    except Exception as exc:  # noqa: BLE001 - structured diagnostics at the isolated process boundary
        response = WorkerResponse(
            bundle_digest=sys.argv[2],
            checks=(),
            error=f"{type(exc).__name__}: {str(exc)[:2000]}",
            diagnostic=read_diagnostic(),
        )
    print(response.model_dump_json())


if __name__ == "__main__":
    main()
