"""Host authorization/audit boundary for credential-free live worker requests."""

import json
import time
from pathlib import Path
from threading import Lock

from simulation_core.execution import JobManifest
from simulation_core.model_gateway import BoundedGateway, GatewayError, ModelGateway, ModelRequest

from .authoring import private_json
from .execution_settings import ActorExecutionSettings

PREFIX = "HYPOTHESIS_MODEL_REQUEST:"


class ActorRelay:
    def __init__(
        self,
        gateway: ModelGateway,
        model: str,
        job: JobManifest,
        audit: Path,
        *,
        settings: ActorExecutionSettings | None = None,
    ) -> None:
        self.settings = settings or ActorExecutionSettings(model=model)
        if self.settings.model != model:
            raise ValueError("Actor settings and relay model must agree")
        self.settings.validate_budget(job.simulation)
        self.gateway = BoundedGateway(
            gateway,
            max_calls=self.settings.max_total_calls,
            max_output_tokens_per_call=self.settings.max_output_tokens,
        )
        self.model = model
        self.actors = {actor.id for actor in job.simulation.world.actors}
        self.audit = audit
        self.calls = 0
        self.replayed = 0
        self._lock = Lock()
        self._active: dict[int, tuple[str, float]] = {}
        self._last_heartbeat = time.monotonic()

    def heartbeat(self) -> None:
        now = time.monotonic()
        if now - self._last_heartbeat < 15:
            return
        self._last_heartbeat = now
        with self._lock:
            active = tuple(self._active.values())
        if active:
            print(
                "[actors] waiting: "
                + ", ".join(f"{actor} {now - started:.0f}s" for actor, started in active),
                flush=True,
            )

    @property
    def provider_attempts(self) -> int:
        return int(getattr(self.gateway.gateway, "new_calls", self.calls - self.replayed))

    def exchange(self, line: str) -> str | None:
        if not line.startswith(PREFIX):
            return None
        with self._lock:
            self.calls += 1
            call_id = self.calls
        started = time.monotonic()
        transport_id = None
        entry: dict[str, object] = {}
        reply: dict[str, object]
        try:
            envelope = json.loads(line[len(PREFIX) :])
            if not isinstance(envelope, dict):
                raise TypeError("Malformed request envelope")
            transport_id = envelope.get("transport_id")
            payload = envelope.get("request", envelope)
            request = ModelRequest.model_validate_json(json.dumps(payload))
            if request.actor_id not in self.actors or request.model != self.model:
                raise GatewayError("unauthorized_actor_or_model")
            if (
                request.reasoning_effort != self.settings.reasoning_effort
                or not request.response_strict
            ):
                raise GatewayError("unsupported_actor_request_options")
            entry["request"] = request.model_dump(mode="json")
            with self._lock:
                self._active[call_id] = (request.actor_id, started)
            print(f"Live actor call {call_id}: {request.actor_id} ({self.model})", flush=True)
            response = self.gateway.complete(request)
            if getattr(self.gateway.gateway, "last_replayed", False):
                with self._lock:
                    self.replayed += 1
                entry["replayed"] = True
            entry["response"] = response.model_dump(mode="json")
            reply = {"response": response.model_dump(mode="json")}
        except GatewayError as exc:
            if getattr(self.gateway.gateway, "last_replayed", False):
                with self._lock:
                    self.replayed += 1
                entry["replayed"] = True
            entry["error"] = str(exc)
            metadata = {
                "request_id": exc.request_id,
                "input_tokens": exc.input_tokens,
                "output_tokens": exc.output_tokens,
                "recorded_request": exc.recorded_request,
            }
            entry["error_metadata"] = metadata
            reply = {"error": str(exc), "error_metadata": metadata}
        except (ValueError, TypeError):
            entry["error"] = "invalid_actor_request"
            reply = {"error": "invalid_actor_request"}
        entry["elapsed_seconds"] = round(time.monotonic() - started, 4)
        with self._lock:
            self._active.pop(call_id, None)
        entry["call_id"] = call_id
        private_json(self.audit / f"actor-{call_id:04d}.json", entry)
        if transport_id is not None:
            reply["transport_id"] = transport_id
        return json.dumps(reply)
