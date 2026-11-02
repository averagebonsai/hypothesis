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
from typing import cast

from pydantic import BaseModel

from agent_tools.bundles import verify_bundle
from agent_tools.process import bounded_command
from agent_tools.specs import BundleManifest, CheckResult, WorkerResponse
from components.library import standard_registry
from simulation_core.execution import JobManifest, JobRunner, LocalBackend
from simulation_core.mechanism import Mechanism
from simulation_core.policy import Policy
from simulation_core.protocol import ProtocolRules
from simulation_core.registry import ComponentRegistry
from simulation_core.solver import GameView, Solver

APPROVED_DEPENDENCIES = frozenset({"numpy", "scipy", "pydantic", "python-dotenv"})
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
    job = JobManifest.model_validate_json(Path("/job/manifest.json").read_text())
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
                    "/opt/toolkit/docker/contract_tests.py",
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
            return WorkerResponse(bundle_digest=seal.digest, checks=tuple(checks))
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
        return WorkerResponse(bundle_digest=seal.digest, checks=tuple(checks))
    artifact = JobRunner(LocalBackend(registry)).run(job.request, job.simulation)
    probe_results = []
    probes_path = Path("/job/probes.json")
    if probes_path.exists():
        for value in json.loads(probes_path.read_text()):
            probe = JobManifest.model_validate(value)
            _, fresh_registry = load_registry(root)
            probe_results.append(
                JobRunner(LocalBackend(fresh_registry)).run(probe.request, probe.simulation)
            )
    return WorkerResponse(
        bundle_digest=seal.digest,
        checks=tuple(checks),
        result=artifact,
        probe_results=tuple(probe_results),
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
            bundle_digest=sys.argv[2], checks=(), error=f"{type(exc).__name__}: {str(exc)[:2000]}"
        )
    print(response.model_dump_json())


if __name__ == "__main__":
    main()
