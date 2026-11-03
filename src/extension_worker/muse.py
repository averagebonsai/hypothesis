"""Trusted entrypoint and file assembler for the containerized Muse CLI."""

import json
import os
import shutil
import sys
from pathlib import Path

from agent_tools.authoring import safe_source_path
from agent_tools.contracts import (
    CodingPlan,
    Implementation,
    ImplementationResponse,
    NotebookReview,
    PlanningResponse,
    ReviewRequest,
    SourceFile,
)
from agent_tools.process import bounded_command
from simulation_core.model_gateway import ModelResponse

ROOT = Path("/workspace")
INPUTS = Path("/inputs")


def update_session_inputs(source: Path) -> None:
    """Offline controller helper: replace inputs, retain workspace notes and CLI home."""
    if os.geteuid() != 0 or not Path("/.dockerenv").exists():
        raise RuntimeError("Session input updates require the isolated controller helper")
    for directory in (ROOT, Path("/session-home")):
        directory.mkdir(parents=True, exist_ok=True)
        # Docker initializes a named volume with the image directory's ownership.
        # Muse's WORKDIR is already owned by 10001; root without CAP_FOWNER cannot
        # chmod it, and the authoring user already has the necessary access.
        owner = directory.stat().st_uid
        if owner == 0:
            directory.chmod(0o777)
        elif owner != 10001:
            raise ValueError("Unexpected authoring volume ownership")
    INPUTS.mkdir(parents=True, exist_ok=True)
    for path in INPUTS.iterdir():
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
    shutil.copytree(source / "inputs", INPUTS, dirs_exist_ok=True)
    for path in INPUTS.rglob("*"):
        if path.is_symlink():
            raise ValueError("Session inputs cannot contain symlinks")
        path.chmod(0o755 if path.is_dir() else 0o644)
    os.setgid(10001)
    os.setuid(10001)
    # Only controller-returned/normalized sources overlay the persistent workspace.
    # Scratch files, notes and prototypes from earlier stages otherwise survive.
    for path in (source / "workspace").rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source / "workspace")
        target = ROOT / relative
        if any(parent.is_symlink() for parent in (target, *target.parents)):
            raise ValueError("Cannot overlay a symlinked workspace path")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.parent.chmod(0o777)
        target.write_bytes(path.read_bytes())
        target.chmod(0o666)
    rules = ROOT / "AGENTS.md"
    if not rules.exists() and not rules.is_symlink():
        rules.symlink_to(INPUTS / "AGENTS.md")


def begin_stage() -> None:
    """A fresh response is required for every turn; previous scratch/context stays."""
    for name in ("response.json", "review.json", "notebook_review.json"):
        path = ROOT / name
        if path.is_dir() and not path.is_symlink():
            raise ValueError("Reserved response path is a directory")
        path.unlink(missing_ok=True)


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
    response: NotebookReview | PlanningResponse | ImplementationResponse
    review_path = ROOT / "review.json"
    if task["stage"] == "review_notebook":
        response = NotebookReview.model_validate_json(read_text(ROOT / "notebook_review.json"))
    elif review_path.exists():
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


def snapshot_workspace(root: Path) -> dict[str, str]:
    """Bounded data-only salvage, never import partial implementations."""
    files: dict[str, str] = {}
    total = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if relative not in {
            "draft.json",
            "response.json",
            "summary.txt",
            "review.json",
            "notebook_review.json",
            "README.md",
        } and not (
            relative.startswith(("tests/", "experiment_extension/")) and path.suffix == ".py"
        ):
            continue
        if any(parent.is_symlink() for parent in (path, *path.parents) if parent != root.parent):
            raise ValueError("Cannot salvage symlinked files")
        if path.is_file():
            text = read_text(path, 600_000)
            total += len(text.encode())
            if total > 4_000_000 or len(files) >= 200:
                raise ValueError("Partial workspace exceeds snapshot budget")
            files[relative] = text
    return files


def main() -> None:
    if sys.argv[1:] == ["update-session"]:
        update_session_inputs(Path("/source"))
        return
    if sys.argv[1:] == ["snapshot"]:
        print(json.dumps(snapshot_workspace(ROOT)))
        return
    if sys.argv[1:] == ["assemble"]:
        assemble()
        return
    if len(sys.argv) != 4:
        raise SystemExit(
            "Usage: python -m extension_worker.muse MODEL EFFORT SESSION_UUID | assemble"
        )
    if not Path("/.dockerenv").is_file() or os.geteuid() != 10001:
        raise RuntimeError("Muse authoring must run inside its restricted Docker container")
    print("HYPOTHESIS_MUSE_AUTH", flush=True)
    auth = json.loads(sys.stdin.readline(20000))
    key = auth["api_key"]
    home = Path(os.environ["HOME"])
    home.mkdir(parents=True, exist_ok=True)
    begin_stage()
    task = json.loads((INPUTS / "task.json").read_text())
    prompt = ROOT / ".stage-prompt.md"
    prompt.write_text(
        (
            (INPUTS / "AGENTS.md").read_text() + "\n\n"
            if not task.get("authoring_session", {}).get("continuation")
            else ""
        )
        + "Continue this same experiment and session. Current stage: "
        + task["stage"]
        + ".\n"
        "Read /inputs/task.json and /inputs/response-schema.json for the current contract/feedback. "
        "Retain earlier discoveries and decisions; do not repeat completed work. "
        "Follow /inputs/AGENTS.md and the completion checklist. "
        "The workspace and your conversation are retained from earlier stages. "
        "Frozen tests/configuration remain controller-owned. Write and assemble a NEW response.json.\n"
    )

    def progress(line: str) -> str | None:
        print(line.replace(key, "[REDACTED]"), flush=True)
        return None

    # Docker is the OS isolation boundary. No host workspace, home, socket or
    # previous sessions are mounted; nested bubblewrap needs unavailable privileges.
    result = bounded_command(
        [
            "muse",
            "exec",
            "--session-id",
            sys.argv[3],
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
            str(prompt),
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
    if task["stage"] == "review_notebook":
        NotebookReview.model_validate_json(text)
    elif task["stage"] == "plan_and_tests":
        PlanningResponse.model_validate_json(text)
    else:
        ImplementationResponse.model_validate_json(text)
    response = ModelResponse(text=text, model=sys.argv[1])
    print("HYPOTHESIS_MUSE_RESULT:" + response.model_dump_json(), flush=True)


if __name__ == "__main__":
    main()
