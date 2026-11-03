"""One offline completion command inside the isolated authoring container."""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal
from uuid import uuid4

from pydantic import Field

from agent_tools.authoring import materialize
from agent_tools.bundles import seal_bundle
from agent_tools.contracts import CandidateResponse, ImplementationResponse
from agent_tools.decision_ledger import atomic_json
from agent_tools.planning import review_plan
from agent_tools.process import ProcessResult, bounded_command
from agent_tools.workspace import candidate_from_workspace, collect_sources, read_source
from simulation_core.execution import JobManifest
from simulation_core.request import ExperimentRequest
from simulation_core.types import FrozenModel

from .runtime import load_registry, require_container

CHECKS = ("lint", "metadata", "types", "tests", "composition", "preview")


class AuthorCheckResult(FrozenModel):
    name: str
    passed: bool
    cached: bool = False
    seconds: float = Field(default=0, ge=0)
    output: str = ""


class AuthorCheckReport(FrozenModel):
    invocation_id: str = Field(default_factory=lambda: uuid4().hex)
    results: tuple[AuthorCheckResult, ...]
    ready: bool
    changed_files: tuple[str, ...]
    files: dict[str, str]
    seconds: float


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _files(root: Path) -> dict[str, str]:
    sources = (*collect_sources(root, "experiment_extension"), *collect_sources(root, "tests"))
    files = {source.path: hashlib.sha256(source.content.encode()).hexdigest() for source in sources}
    for name in ("draft.json", "summary.txt", "README.md"):
        if (root / name).exists():
            files[name] = hashlib.sha256(read_source(root / name).encode()).hexdigest()
    return files


def _key(name: str, files: dict[str, str], context: object) -> str:
    selected = dict(files)
    if name == "types":
        selected = {p: v for p, v in files.items() if p.startswith("experiment_extension/")}
    elif name in {"preview", "composition"}:
        selected = {
            p: v
            for p, v in files.items()
            if not p.startswith("tests/") and p not in {"summary.txt", "README.md"}
        }
    elif name == "metadata":
        selected = {
            p: ("present" if p.startswith("experiment_extension/") else v) for p, v in files.items()
        }
    return _hash((name, selected, context))


def execute_workspace_phase(
    root: Path, inputs: Path, phase: Literal["composition", "preview"]
) -> None:
    """Only subprocesses in Docker import experimental Python; no live relay is opened."""
    require_container()
    os.environ.pop("HYPOTHESIS_ACTOR_RELAY", None)
    task = json.loads((inputs / "task.json").read_text())
    candidate = candidate_from_workspace(root, task)
    request = ExperimentRequest.model_validate_json(json.dumps(task["request"]))
    with TemporaryDirectory(prefix="author-check-bundle-") as temporary:
        bundle = Path(temporary) / candidate.plan.bundle.experiment_id / "v1"
        job = materialize(bundle, request, candidate.plan, candidate.implementation, 1)
        seal_bundle(bundle)
        manifest, registry = load_registry(bundle)
        if isinstance(job, JobManifest):
            registry.validate_config(job.simulation)
            if phase == "preview":
                if manifest.notebook is None:
                    raise ValueError("Simulation requires an offline preview generator")
                from .reporting import execute_preview

                execute_preview(job, manifest.notebook)
        elif phase == "composition":
            # Validate typed tool arguments without executing the computation.
            import importlib
            import inspect

            from pydantic import BaseModel

            component = next(
                (c for c in manifest.components if c.symbol == job.tool.entrypoint), None
            )
            arguments = dict(job.tool.arguments)
            if component and component.input_model:
                module, name = component.input_model.split(":")
                model = getattr(importlib.import_module(module), name)
                if not isinstance(model, type) or not issubclass(model, BaseModel):
                    raise TypeError("Tool input contract must be a Pydantic class")
                arguments = model.model_validate_json(json.dumps(arguments)).model_dump()
            module, name = job.tool.entrypoint.split(":")
            inspect.signature(getattr(importlib.import_module(module), name)).bind(**arguments)


def run_author_checks(
    root: Path,
    inputs: Path,
    project: Path,
    *,
    only: tuple[str, ...] = CHECKS,
    use_cache: bool = True,
) -> AuthorCheckReport:
    require_container()
    if set(only) - set(CHECKS):
        raise ValueError("Unknown author-check section")
    started = time.monotonic()
    root = root.resolve()
    cache_dir = root / ".author-check"
    if cache_dir.is_symlink():
        raise ValueError("Author-check directory cannot be a link")
    cache_dir.mkdir(exist_ok=True)
    response_path = root / "response.json"
    if response_path.is_symlink():
        raise ValueError("Response cannot be a link")
    response_path.unlink(missing_ok=True)
    task = json.loads((inputs / "task.json").read_text())
    context = {
        k: task.get(k)
        for k in ("request", "experiment_id", "frozen_plan", "execution_capabilities")
    }
    context["framework"] = _hash(
        {
            str(p.relative_to(project)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((project / "src").rglob("*.py"))
        }
        | {
            name: hashlib.sha256((project / name).read_bytes()).hexdigest()
            for name in ("pyproject.toml", "uv.lock")
            if (project / name).exists()
        }
    )
    cache_path = cache_dir / "cache.json"
    previous = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    initial_files = _files(root)
    old_files = previous.get("files", {})
    changed = tuple(
        sorted(
            p
            for p in initial_files.keys() | old_files.keys()
            if initial_files.get(p) != old_files.get(p)
        )
    )
    cache: dict[str, Any] = dict(previous.get("checks", {}))
    results = []
    for name in CHECKS:
        fingerprint = _key(name, _files(root), context)
        saved = cache.get(name, {})
        if use_cache and saved.get("fingerprint") == fingerprint and saved.get("passed"):
            results.append(
                AuthorCheckResult(
                    name=name,
                    passed=True,
                    cached=True,
                    output="Unchanged inputs; previous check passed",
                )
            )
            continue
        if name not in only:
            continue
        mark = time.monotonic()
        try:
            if name == "metadata":
                candidate = candidate_from_workspace(root, task)
                request = ExperimentRequest.model_validate_json(json.dumps(task["request"]))
                issues = review_plan(
                    project,
                    request,
                    candidate.plan.bundle.experiment_id,
                    candidate.plan,
                    lint_tests=False,
                )
                if issues:
                    raise ValueError("\n".join(issues))
                output = "Configuration, exports and declared test contracts passed"
                passed = True
            else:
                base = [sys.executable, "-m", "ruff"]
                targets = [str(root / "experiment_extension"), str(root / "tests")]
                config = ["--config", str(project / "pyproject.toml")]

                def command(args: list[str], seconds: int = 90) -> ProcessResult:
                    environment = {
                        key: value
                        for key, value in os.environ.items()
                        if key
                        not in {
                            "API_KEY",
                            "OPENAI_API_KEY",
                            "HYPOTHESIS_ACTOR_RELAY",
                            "HYPOTHESIS_ENABLE_ACTORS",
                        }
                        and not key.startswith("API_KEY_")
                    }
                    return bounded_command(
                        args, seconds=seconds, max_bytes=150000, cwd=root, env=environment
                    )

                if name == "lint":
                    command(base + ["check", "--select", "I", "--fix", *config, *targets])
                    command(base + ["format", *config, *targets])
                    result = command(base + ["check", "--no-cache", *config, *targets])
                elif name == "types":
                    result = command(
                        [
                            sys.executable,
                            "-m",
                            "mypy",
                            *config,
                            "--cache-dir",
                            str(cache_dir / "mypy"),
                            targets[0],
                        ]
                    )
                elif name == "tests":
                    tests = task.get("frozen_tests_directory", str(root / "tests"))
                    result = command(
                        [
                            sys.executable,
                            "-m",
                            "pytest",
                            "-q",
                            "-p",
                            "no:cacheprovider",
                            "-c",
                            str(project / "docker/pytest.ini"),
                            tests,
                        ]
                    )
                else:
                    result = command(
                        [
                            sys.executable,
                            "-m",
                            "extension_worker.author_check",
                            "--workspace",
                            str(root),
                            "--inputs",
                            str(inputs),
                            "--phase",
                            name,
                        ]
                    )
                output, passed = (result.stdout + result.stderr)[-12000:], result.code == 0
            result_record = AuthorCheckResult(
                name=name, passed=passed, seconds=time.monotonic() - mark, output=output
            )
        except (ValueError, TypeError, KeyError, OSError, RuntimeError, SyntaxError) as exc:
            result_record = AuthorCheckResult(
                name=name,
                passed=False,
                seconds=time.monotonic() - mark,
                output=f"{type(exc).__name__}: {exc}",
            )
        results.append(result_record)
        # A test/preview must not rewrite the candidate it claims to have checked.
        after = _key(name, _files(root), context)
        if name != "lint" and after != fingerprint:
            result_record = result_record.model_copy(
                update={
                    "passed": False,
                    "output": "Check changed its own source/configuration inputs; rerun after correcting the side effect",
                }
            )
            results[-1] = result_record
        cache[name] = {"fingerprint": after, "passed": result_record.passed}
        print(
            f"[author-check] {name}: {'passed' if result_record.passed else 'failed'} ({result_record.seconds:.2f}s)",
            flush=True,
        )
    final_files = _files(root)
    changed = tuple(
        sorted(
            set(changed)
            | {
                p
                for p in initial_files.keys() | final_files.keys()
                if initial_files.get(p) != final_files.get(p)
            }
        )
    )
    ready = all(
        cache.get(name, {}).get("passed")
        and cache[name].get("fingerprint") == _key(name, final_files, context)
        for name in CHECKS
    )
    report = AuthorCheckReport(
        results=tuple(results),
        ready=ready,
        changed_files=changed,
        files=final_files,
        seconds=time.monotonic() - started,
    )
    atomic_json(cache_path, {"files": final_files, "checks": cache})
    atomic_json(cache_dir / "report.json", report.model_dump(mode="json"))
    with (cache_dir / "history.jsonl").open("a") as stream:
        stream.write(report.model_dump_json() + "\n")
    if ready:
        candidate = candidate_from_workspace(root, task)
        response = (
            ImplementationResponse(implementation=candidate.implementation, review=None)
            if task["stage"] in {"implementation", "repair_implementation"}
            else CandidateResponse(candidate=candidate, review=None)
        )
        atomic_json(response_path, response.model_dump(mode="json"))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--inputs", type=Path, default=Path("/inputs"))
    parser.add_argument("--project", type=Path, default=Path("/opt/toolkit"))
    parser.add_argument("--only", nargs="+", choices=CHECKS)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--phase", choices=("composition", "preview"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.phase:
        execute_workspace_phase(args.workspace, args.inputs, args.phase)
        return
    report = run_author_checks(
        args.workspace,
        args.inputs,
        args.project,
        only=tuple(args.only) if args.only else CHECKS,
        use_cache=not args.no_cache,
    )
    print(report.model_dump_json(indent=2))
    if not report.ready:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
