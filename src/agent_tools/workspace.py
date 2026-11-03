"""Data-only workspace collection and mechanical authoring metadata."""

import ast
import json
import re
from pathlib import Path
from typing import Any

from .contracts import AuthoredCandidate, CodingPlan, Implementation, SourceFile


def read_source(path: Path, limit: int = 250000) -> str:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("Missing, linked or oversized workspace source")
    return path.read_text()


def collect_sources(root: Path, directory: str) -> tuple[SourceFile, ...]:
    from .authoring import safe_source_path

    folder = root / directory
    if folder.is_symlink():
        raise ValueError("Workspace source directory cannot be a link")
    result = []
    for path in sorted(folder.rglob("*")):
        if path.is_symlink():
            raise ValueError("Workspace sources cannot contain links")
        if path.is_file() and path.suffix == ".py":
            relative = path.relative_to(root).as_posix()
            if not safe_source_path(relative, tests=directory == "tests"):
                raise ValueError("Unsafe workspace source path")
            result.append(SourceFile(path=relative, content=read_source(path)))
    return tuple(result)


def component_id(experiment_id: str, kind: str, symbol_name: str) -> str:
    """Use this helper when a draft needs to reference an automatically named export."""
    if not re.fullmatch(r"[a-z][a-z0-9_]*", experiment_id):
        raise ValueError("Invalid experiment namespace")
    if not kind.isidentifier() or not symbol_name.isidentifier():
        raise ValueError("Component names must be identifiers")
    return f"experimental.{experiment_id}.{kind}.{symbol_name.lower()}.v1"


def test_index(tests: tuple[SourceFile, ...]) -> dict[str, list[str]]:
    return {
        source.path: [
            node.name
            for node in ast.parse(source.content).body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        ]
        for source in tests
    }


def candidate_from_workspace(root: Path, task: dict[str, Any]) -> AuthoredCandidate:
    """Never import authored Python. Domain expectations still come from the author."""
    files = collect_sources(root, "experiment_extension")
    if (root / "README.md").exists():
        files += (SourceFile(path="README.md", content=read_source(root / "README.md")),)
    if task.get("stage") in {"implementation", "repair_implementation"}:
        plan = CodingPlan.model_validate_json(json.dumps(task["frozen_plan"]))
    else:
        tests = collect_sources(root, "tests")
        draft = json.loads(read_source(root / "draft.json"))
        manifest = draft["bundle"]
        experiment_id = task["experiment_id"]
        manifest.setdefault("experiment_id", experiment_id)
        manifest.setdefault("version", "v1")
        index = test_index(tests)
        for component in manifest.get("components", []):
            component.setdefault(
                "id",
                component_id(experiment_id, component["kind"], component["symbol"].split(":")[1]),
            )
            groups = component.pop("test_groups", [])
            declared = component.setdefault("acceptance_tests", [])
            for group in groups:
                names = index.get(group["file"], [])
                if not names:
                    raise ValueError(f"No tests discovered in {group['file']}")
                declared.extend(
                    {
                        "name": name,
                        "category": group["category"],
                        "expected": group["expected"],
                        "reference": group["reference"],
                    }
                    for name in names
                )
        if manifest.get("notebook") is not None:
            manifest["notebook"].setdefault("report_version", "explanatory.v1")
        draft["tests"] = [source.model_dump(mode="json") for source in tests]
        plan = CodingPlan.model_validate_json(json.dumps(draft))
    summary_path = root / "summary.txt"
    summary = read_source(summary_path, 3000).strip() if summary_path.exists() else plan.summary
    return AuthoredCandidate(plan=plan, implementation=Implementation(summary=summary, files=files))
