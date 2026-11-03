"""Explicit current-run snapshots: committed events are the canonical state record."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import Field

from .types import Decision, Event, FrozenModel, ModelCallRecord, SimulationConfig


def config_digest(config: SimulationConfig) -> str:
    canonical = json.dumps(config.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class RuntimeCheckpoint(FrozenModel):
    config_digest: str
    events: tuple[Event, ...] = Field(min_length=1)
    pending: dict[str, Decision] = Field(default_factory=dict)
    pending_calls: dict[str, tuple[ModelCallRecord, ...]] = Field(default_factory=dict)

    @classmethod
    def create(
        cls,
        config: SimulationConfig,
        events: tuple[Event, ...],
        pending: dict[str, Decision],
        calls: dict[str, tuple[ModelCallRecord, ...]],
    ) -> "RuntimeCheckpoint":
        return cls(
            config_digest=config_digest(config), events=events, pending=pending, pending_calls=calls
        ).model_copy(deep=True)

    def validate_config(self, config: SimulationConfig) -> None:
        if self.config_digest != config_digest(config):
            raise ValueError("Checkpoint configuration mismatch")
        if any(aid != decision.action.actor_id for aid, decision in self.pending.items()):
            raise ValueError("Checkpoint action ownership mismatch")


def merge_checkpoint(previous: dict | None, delta: dict) -> RuntimeCheckpoint:
    """Merge append-only event transport; reject omitted or rewritten commits."""
    payload = dict(delta)
    count = payload.pop("event_count")
    events = list(previous["events"]) if previous is not None else []
    if previous is not None and previous["config_digest"] != payload["config_digest"]:
        raise ValueError("Checkpoint configuration changed")
    for event in payload["events"]:
        index = event["sequence"]
        if index == len(events):
            events.append(event)
        elif not 0 <= index < len(events) or events[index] != event:
            raise ValueError("Checkpoint rewrites or skips a committed event")
    if len(events) != count:
        raise ValueError("Checkpoint event count mismatch")
    payload["events"] = events
    checkpoint = RuntimeCheckpoint.model_validate_json(json.dumps(payload))
    from .logging import replay

    replay(checkpoint.events)
    return checkpoint


@dataclass(frozen=True)
class RuntimeOptions:
    max_concurrency: int = 1
    checkpoint: RuntimeCheckpoint | None = None
    on_checkpoint: Callable[[RuntimeCheckpoint], None] | None = None
    on_timing: Callable[[dict[str, str | int | float]], None] | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.max_concurrency <= 32:
            raise ValueError("Concurrency must be between 1 and 32")
