"""Host authorization/audit boundary for credential-free live worker requests."""

import json
from pathlib import Path

from simulation_core.execution import JobManifest
from simulation_core.model_gateway import BoundedGateway, GatewayError, ModelGateway, ModelRequest

from .authoring import private_json

PREFIX = "HYPOTHESIS_MODEL_REQUEST:"


class ActorRelay:
    def __init__(self, gateway: ModelGateway, model: str, job: JobManifest, audit: Path) -> None:
        self.gateway = BoundedGateway(gateway, max_calls=48, max_output_tokens_per_call=4096)
        self.model = model
        self.actors = {actor.id for actor in job.simulation.world.actors}
        self.audit = audit
        self.calls = 0

    def exchange(self, line: str) -> str | None:
        if not line.startswith(PREFIX):
            return None
        self.calls += 1
        entry: dict[str, object] = {}
        reply: dict[str, object]
        try:
            request = ModelRequest.model_validate_json(line[len(PREFIX) :])
            if request.actor_id not in self.actors or request.model != self.model:
                raise GatewayError("unauthorized_actor_or_model")
            if request.reasoning_effort is not None or not request.response_strict:
                raise GatewayError("unsupported_actor_request_options")
            entry["request"] = request.model_dump(mode="json")
            print(f"Live actor call {self.calls}: {request.actor_id} ({self.model})", flush=True)
            response = self.gateway.complete(request)
            entry["response"] = response.model_dump(mode="json")
            reply = {"response": response.model_dump(mode="json")}
        except GatewayError as exc:
            entry["error"] = str(exc)
            reply = {"error": str(exc)}
        except ValueError:
            entry["error"] = "invalid_actor_request"
            reply = {"error": "invalid_actor_request"}
        private_json(self.audit / f"actor-{self.calls:04d}.json", entry)
        return json.dumps(reply)
