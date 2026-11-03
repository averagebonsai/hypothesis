"""Resume a deterministic current-trial prefix without asking actors again.

Callers explicitly supply accepted responses from this experiment. No filesystem
search or historical experiment retrieval occurs here. Request equality prevents
reusing a decision under changed observations, policy instructions or schemas.
"""

import json
from typing import Literal

from simulation_core.model_gateway import GatewayError, ModelGateway, ModelRequest, ModelResponse


class RecordedPrefixGateway(ModelGateway):
    def __init__(
        self,
        gateway: ModelGateway,
        prefix: tuple[tuple[ModelRequest, ModelResponse | GatewayError], ...],
        *,
        allow_output_budget_change: bool = False,
    ):
        self.gateway = gateway
        self.prefix = prefix
        self.index = 0
        self.new_calls = 0
        self.last_replayed = False
        self.allow_output_budget_change = allow_output_budget_change

    @property
    def mode(self) -> Literal["fake", "live"]:
        return self.gateway.mode

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.last_replayed = False
        if self.index < len(self.prefix):
            expected, response = self.prefix[self.index]
            excluded = (
                {"input_json", "max_output_tokens"}
                if self.allow_output_budget_change
                else {"input_json"}
            )
            if expected.model_dump(exclude=excluded) != request.model_dump(
                exclude=excluded
            ) or json.loads(expected.input_json) != json.loads(request.input_json):
                raise GatewayError("recorded_prefix_request_mismatch")
            self.index += 1
            self.last_replayed = True
            print(
                f"Reusing accepted current-trial response {self.index}: {request.actor_id}",
                flush=True,
            )
            if isinstance(response, GatewayError):
                raise GatewayError(
                    str(response),
                    request_id=response.request_id,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    recorded_request=expected.model_dump(mode="json"),
                )
            return response.model_copy(
                deep=True, update={"recorded_request": expected.model_dump(mode="json")}
            )
        self.new_calls += 1
        return self.gateway.complete(request)
