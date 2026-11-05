"""In-memory job tracking and SSE broadcasting."""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class JobState:
    job_id: str
    kind: str  # "preset" | "custom"
    scenario_id: str
    status: str  # "pending" | "authoring" | "running" | "completed" | "failed"
    created_at: float = field(default_factory=time.time)
    parameters: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    payoffs: dict[str, float] = field(default_factory=dict)
    notebook_data: dict[str, Any] | None = None
    error: str | None = None
    listeners: list[asyncio.Queue[str | None]] = field(default_factory=list)

    def broadcast(self, data: dict[str, Any]) -> None:
        message = f"data: {json.dumps(data)}\n\n"
        for queue in self.listeners:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                pass

    def finish(self, status: str = "completed", error: str | None = None) -> None:
        self.status = status
        self.error = error
        final_payload = {
            "type": "finished",
            "job_id": self.job_id,
            "status": status,
            "error": error,
            "payoffs": self.payoffs,
            "metrics": self.metrics,
        }
        self.broadcast(final_payload)
        for queue in self.listeners:
            try:
                queue.put_nowait(None)  # Signal stream end
            except asyncio.QueueFull:
                pass


class JobManager:
    """Thread-safe registry of live and finished simulation jobs."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobState] = {}

    def create_job(self, kind: str, scenario_id: str, parameters: dict[str, Any]) -> JobState:
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        state = JobState(job_id=job_id, kind=kind, scenario_id=scenario_id, status="pending", parameters=parameters)
        self._jobs[job_id] = state
        return state

    def get_job(self, job_id: str) -> JobState | None:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[dict[str, Any]]:
        return [
            {
                "job_id": j.job_id,
                "kind": j.kind,
                "scenario_id": j.scenario_id,
                "status": j.status,
                "created_at": j.created_at,
                "error": j.error,
            }
            for j in self._jobs.values()
        ]


JOBS = JobManager()
