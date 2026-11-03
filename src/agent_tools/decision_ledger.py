"""Durable, request-keyed responses for one explicitly selected worker execution."""

import hashlib
import json
import os
from pathlib import Path
from threading import Lock, local
from typing import Literal

from simulation_core.model_gateway import GatewayError, ModelGateway, ModelRequest, ModelResponse


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


class DecisionLedger(ModelGateway):
    def __init__(
        self,
        gateway: ModelGateway,
        directory: Path,
        *,
        max_calls: int | None = None,
        max_calls_per_actor: int | dict[str, int] | None = None,
    ) -> None:
        self.gateway = gateway
        self.directory = directory
        self._locks: dict[str, Lock] = {}
        self._lock = Lock()
        self._local = local()
        self.max_calls = max_calls
        self.max_calls_per_actor = max_calls_per_actor
        self.new_calls = 0

    @property
    def mode(self) -> Literal["fake", "live"]:
        return self.gateway.mode

    @property
    def last_replayed(self) -> bool:
        return bool(getattr(self._local, "replayed", False))

    @property
    def route_metadata(self) -> dict[str, int | float]:
        return getattr(self._local, "route", {})

    def complete(self, request: ModelRequest) -> ModelResponse:
        self._local.replayed = False
        self._local.route = {}
        # Canonicalize JSON; never retrieve from a different trial or changed request.
        value = request.model_dump(mode="json")
        value["input_json"] = json.loads(request.input_json)
        key = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
        with self._lock:
            lock = self._locks.setdefault(key, Lock())
        with lock:
            path = self.directory / (key + ".json")
            pending = self.directory / (key + ".pending")
            if path.exists():
                saved = json.loads(path.read_text())
                if saved["request"] != value:
                    raise ValueError("Decision ledger request mismatch")
                self._local.replayed = True
                return ModelResponse.model_validate(saved["response"])
            if pending.exists():
                raise GatewayError("pending_provider_outcome_unresolved")
            with self._lock:
                usage_path = self.directory / "usage.json"
                usage = json.loads(usage_path.read_text()) if usage_path.exists() else {}
                actor_limit = (
                    self.max_calls_per_actor.get(request.actor_id)
                    if isinstance(self.max_calls_per_actor, dict)
                    else self.max_calls_per_actor
                )
                if (self.max_calls is not None and sum(usage.values()) >= self.max_calls) or (
                    actor_limit is not None and usage.get(request.actor_id, 0) >= actor_limit
                ):
                    raise GatewayError("durable_call_budget_exhausted")
                usage[request.actor_id] = usage.get(request.actor_id, 0) + 1
                # Reserve before calling: unknown outcomes after a crash still consume budget.
                atomic_json(usage_path, usage)
            atomic_json(pending, {"request": value})
            with self._lock:
                self.new_calls += 1
            try:
                response = self.gateway.complete(request)
            except GatewayError:
                pending.unlink(missing_ok=True)
                raise
            finally:
                self._local.route = getattr(self.gateway, "route_metadata", {})
            atomic_json(path, {"request": value, "response": response.model_dump(mode="json")})
            pending.unlink(missing_ok=True)
            return response
