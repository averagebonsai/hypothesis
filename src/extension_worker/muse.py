"""Trusted entrypoint and file assembler for the containerized Muse CLI."""

import json
import os
import sys
from pathlib import Path

from agent_tools.authoring import safe_source_path
from agent_tools.contracts import (
    CodingPlan,
    Implementation,
    ImplementationResponse,
    PlanningResponse,
    ReviewRequest,
    SourceFile,
)
from agent_tools.process import bounded_command
from simulation_core.model_gateway import ModelResponse

ROOT = Path("/workspace")
INPUTS = Path("/inputs")


def read_text(path: Path, limit: int = 600_000) -> str:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("Missing, symlinked or oversized authoring file")
    return path.read_text()


def source_files(directory: Path, *, tests: bool) -> tuple[SourceFile, ...]:
    result = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("Authoring sources cannot contain symlinks")
        if path.is_file() and path.suffix == ".py":
            relative = path.relative_to(ROOT).as_posix()
            if not safe_source_path(relative, tests=tests):
                raise ValueError("Invalid authoring source path")
            result.append(SourceFile(path=relative, content=read_text(path, 250000)))
    return tuple(result)


def assemble() -> None:
    """Build native response objects from ordinary source files, without imports."""
    task = json.loads((INPUTS / "task.json").read_text())
    review_path = ROOT / "review.json"
    if review_path.exists():
        review = ReviewRequest.model_validate_json(read_text(review_path))
        response = (
            PlanningResponse(plan=None, review=review)
            if task["stage"] == "plan_and_tests"
            else ImplementationResponse(implementation=None, review=review)
        )
    elif task["stage"] == "plan_and_tests":
        draft = json.loads(read_text(ROOT / "draft.json"))
        draft["tests"] = [
            file.model_dump(mode="json") for file in source_files(ROOT / "tests", tests=True)
        ]
        response = PlanningResponse(
            plan=CodingPlan.model_validate_json(json.dumps(draft)), review=None
        )
    else:
        files = source_files(ROOT / "experiment_extension", tests=False)
        readme = ROOT / "README.md"
        if readme.exists():
            files += (SourceFile(path="README.md", content=read_text(readme, 250000)),)
        implementation = Implementation(summary=read_text(ROOT / "summary.txt", 3000), files=files)
        response = ImplementationResponse(implementation=implementation, review=None)
    (ROOT / "response.json").write_text(response.model_dump_json(indent=2))
    print("Validated response.json; no experiment code was imported")


def main() -> None:
    if sys.argv[1:] == ["assemble"]:
        assemble()
        return
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python -m extension_worker.muse MODEL EFFORT | assemble")
    if not Path("/.dockerenv").is_file() or os.geteuid() != 10001:
        raise RuntimeError("Muse authoring must run inside its restricted Docker container")
    print("HYPOTHESIS_MUSE_AUTH", flush=True)
    auth = json.loads(sys.stdin.readline(20000))
    key = auth["api_key"]
    home = Path(os.environ["HOME"])
    home.mkdir(parents=True, exist_ok=True)

    def progress(line: str) -> str | None:
        print(line.replace(key, "[REDACTED]"), flush=True)
        return None

    # Docker is the OS isolation boundary. No host workspace, home, socket or
    # previous sessions are mounted; nested bubblewrap needs unavailable privileges.
    result = bounded_command(
        [
            "muse",
            "exec",
            "--workspace",
            "/workspace",
            "--model",
            sys.argv[1],
            "--reasoning-effort",
            sys.argv[2],
            "-c",
            "agents.execution_capacity=1",
            "--contributor-mode",
            "off",
            "--json",
            "--yolo",
            "--api-key-stdin",
            "--disable-web-tools",
            "--disable-reminders",
            "--disable-request-user-input",
            "--no-foreign-personal-context",
            "--prompt-file",
            "/inputs/AGENTS.md",
        ],
        seconds=3500,
        max_bytes=12_000_000,
        exchange=progress,
        input_text=key + "\n",
    )
    if result.stderr:
        print(result.stderr.replace(key, "[REDACTED]"), file=sys.stderr, flush=True)
    if result.code:
        raise SystemExit(result.code)
    text = read_text(ROOT / "response.json")
    if key in text:
        raise RuntimeError("Authoring output contains a credential; refusing export")
    task = json.loads(Path("/inputs/task.json").read_text())
    if task["stage"] == "plan_and_tests":
        PlanningResponse.model_validate_json(text)
    else:
        ImplementationResponse.model_validate_json(text)
    response = ModelResponse(text=text, model=sys.argv[1])
    print("HYPOTHESIS_MUSE_RESULT:" + response.model_dump_json(), flush=True)


if __name__ == "__main__":
    main()
