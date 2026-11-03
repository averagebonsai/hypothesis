"""Readable, durable progress from native CLI events; raw events stay separate."""

import json
import os
import time
from collections.abc import Callable
from pathlib import Path


class AuthoringProgress:
    def __init__(
        self,
        path: Path,
        stage: str,
        *,
        emit: Callable[[str], None] = print,
        clock: Callable[[], float] = time.monotonic,
        heartbeat_seconds: float = 30,
    ) -> None:
        self.path, self.stage, self.emit, self.clock = path, stage, emit, clock
        self.started = self.last_notice = clock()
        self.heartbeat_seconds = heartbeat_seconds
        self.last_activity = "starting"
        self.tools = self.retries = 0
        self.runs: dict[str, dict[str, object]] = {}
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        self.record("stage_started", stage)

    def record(self, kind: str, message: str, **fields: object) -> None:
        elapsed = round(self.clock() - self.started, 1)
        with self.path.open("a") as stream:
            stream.write(
                json.dumps(
                    dict(
                        kind=kind,
                        stage=self.stage,
                        elapsed_seconds=elapsed,
                        message=message,
                        **fields,
                    )
                )
                + "\n"
            )
        self.last_notice = self.clock()
        self.emit(f"[{self.stage} +{elapsed:.0f}s] {message}")

    def consume(self, event: dict[str, object]) -> None:
        kind = event.get("payload_type", "")
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            return
        if kind == "tool.result":
            self.tools += 1
            facts = payload.get("correlation_facts", {})
            tool = facts.get("tool_name", "tool") if isinstance(facts, dict) else "tool"
            outcome = facts.get("outcome", "completed") if isinstance(facts, dict) else "completed"
            description = str(tool)
            try:
                data = json.loads(str(payload.get("text", "{}")))
                if isinstance(data, dict):
                    description = str(data.get("description") or tool)
            except ValueError:
                pass
            self.last_activity = description[:180]
            self.record(
                "tool_completed", f"{description[:180]} ({outcome})", tool=tool, tools=self.tools
            )
        elif kind == "task.lifecycle.status":
            detail = payload.get("event", {})
            if (
                isinstance(detail, dict)
                and isinstance(detail.get("details"), dict)
                and detail["details"].get("phase") == "retrying"
            ):
                self.retries += 1
                self.last_activity = "provider retry"
                self.record(
                    "provider_retry",
                    str(detail.get("message", "Provider retry"))[:300],
                    retries=self.retries,
                )
        elif kind == "run.model.configured":
            self.record("model_configured", f"Model: {payload.get('model_id', 'unknown')}")
        elif kind == "run.usage":
            identity = payload.get("run_stream", {})
            run_id = str(identity.get("id", "run")) if isinstance(identity, dict) else "run"
            self.runs[run_id] = payload
            self.record("usage", "Provider usage received", **self.usage())
        elif kind in {"run.terminal.completed", "run.terminal.failed", "run.terminal.cancelled"}:
            self.record("cli_terminal", str(kind), tools=self.tools, retries=self.retries)

    def tick(self) -> None:
        if self.clock() - self.last_notice >= self.heartbeat_seconds:
            self.record(
                "heartbeat",
                f"Waiting; last activity: {self.last_activity}; {self.tools} tools completed",
                retries=self.retries,
            )

    def usage(self) -> dict[str, int]:
        totals = {
            "calls": 0,
            "completed_calls": 0,
            "failed_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_tokens": 0,
            "reasoning_tokens": 0,
        }
        for payload in self.runs.values():
            for key in ("calls", "completed_calls", "failed_calls"):
                value = payload.get(key, 0)
                if isinstance(value, int):
                    totals[key] += value
            models = payload.get("models", [])
            if isinstance(models, list):
                for model in models:
                    if isinstance(model, dict):
                        for key in (
                            "input_tokens",
                            "output_tokens",
                            "cached_tokens",
                            "reasoning_tokens",
                        ):
                            value = model.get(key, 0)
                            if isinstance(value, int):
                                totals[key] += value
        return totals
