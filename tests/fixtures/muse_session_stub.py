#!/opt/toolkit/.venv/bin/python
"""Offline integration fixture only; production Muse images exclude all tests."""

import json
import os
import sys
from pathlib import Path

from agent_tools.contracts import (
    Implementation,
    ImplementationResponse,
    PlanningResponse,
    SourceFile,
)


def main() -> None:
    assert sys.stdin.readline().startswith("synthetic-")
    sid = sys.argv[sys.argv.index("--session-id") + 1]
    prompt = Path(sys.argv[sys.argv.index("--prompt-file") + 1]).read_text()
    task = json.loads(Path("/inputs/task.json").read_text())
    home = Path(os.environ["HOME"])
    journal = home / "stub-history.json"
    history = json.loads(journal.read_text()) if journal.exists() else []
    if history:
        assert history[0]["id"] == sid
        assert (
            Path("/workspace/decision-notes.md").read_text()
            == "Use the selected interface; retain this decision."
        )
        assert "GENERIC_INSTRUCTIONS_MARKER" not in prompt
    else:
        assert "GENERIC_INSTRUCTIONS_MARKER" in prompt
        Path("/workspace/decision-notes.md").write_text(
            "Use the selected interface; retain this decision."
        )
        Path("/workspace/prototype.txt").write_text("Trial-local prototype")
    history.append({"id": sid, "stage": task["stage"]})
    journal.write_text(json.dumps(history))
    if task.get("fail"):
        raise SystemExit(7)
    if task["stage"] == "plan_and_tests":
        response = PlanningResponse.model_validate_json(
            json.dumps({"plan": task["test_plan"], "review": None})
        )
    else:
        assert Path("/workspace/prototype.txt").exists()
        frozen = Path(task["frozen_tests_directory"]) / "test_current.py"
        try:
            frozen.write_text("weaken the test")
        except OSError:
            pass
        else:
            raise AssertionError("Frozen tests must remain read-only")
        assert frozen.read_text() == task["frozen_plan"]["tests"][0]["content"]
        if "previous_implementation" in task:
            for file in task["previous_implementation"]["files"]:
                assert (Path("/workspace") / file["path"]).read_text() == file["content"]
        source = f"value = {len(history)}\n"
        package = Path("/workspace/experiment_extension")
        package.mkdir(exist_ok=True)
        (package / "__init__.py").write_text("")
        (package / "component.py").write_text(source)
        response = ImplementationResponse(
            implementation=Implementation(
                summary="Offline session fixture",
                files=(
                    SourceFile(path="experiment_extension/__init__.py", content=""),
                    SourceFile(path="experiment_extension/component.py", content=source),
                ),
            ),
            review=None,
        )
    Path("/workspace/response.json").write_text(response.model_dump_json())
    print(
        json.dumps(
            {
                "payload_type": "run.terminal.completed",
                "stream": {"kind": "session", "id": sid},
                "payload": {},
            }
        )
    )


if __name__ == "__main__":
    main()
