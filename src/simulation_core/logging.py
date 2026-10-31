"""Canonical internal log: includes private state; do not expose it to actors."""

import json
import logging
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import TextIO

from .types import Event, WorldState


def replay(events: Sequence[Event]) -> tuple[WorldState, ...]:
    if not events:
        raise ValueError("Missing initialization")
    snapshots = []
    for index, raw in enumerate(events):
        event = Event.model_validate(raw.model_dump())
        if event.sequence != index or event.kind != ("initialized" if index == 0 else "committed"):
            raise ValueError("Invalid event sequence")
        if event.state.tick != index:
            raise ValueError("Invalid event tick")
        if index == 0 and (event.actions or event.outcome is not None):
            raise ValueError("Initialization cannot contain actions or outcomes")
        if index and event.outcome is None:
            raise ValueError("Commit requires an outcome")
        if (
            event.decisions
            and tuple(decision.action for decision in event.decisions) != event.actions
        ):
            raise ValueError("Decision trace does not match committed actions")
        for call in event.model_calls:
            if call.status == "accepted":
                decision = next(
                    (item for item in event.decisions if item.action.actor_id == call.actor_id),
                    None,
                )
                if (
                    decision is None
                    or not decision.rationale
                    or call.rationale != decision.rationale
                ):
                    raise ValueError("Model-call rationale does not match committed decision")
        snapshots.append(event.state.model_copy(deep=True))
    return tuple(snapshots)


def log_committed_decisions(event: Event) -> None:
    """Emit one JSON log line per committed action; never log uncommitted candidates."""
    logger = logging.getLogger("simulation.actions")
    for decision in event.decisions:
        logger.info(
            json.dumps(
                {
                    "tick": event.state.tick,
                    "actor_id": decision.action.actor_id,
                    "action": decision.action.model_dump(mode="json"),
                    "rationale": decision.rationale,
                },
                ensure_ascii=False,
            )
        )


@contextmanager
def stream_action_trace(stream: TextIO | None = None) -> Iterator[None]:
    """Opt-in application console output; event records are always retained."""
    logger = logging.getLogger("simulation.actions")
    previous_level, previous_propagate = logger.level, logger.propagate
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        yield
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate
