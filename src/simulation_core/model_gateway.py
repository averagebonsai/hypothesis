"""Provider-neutral bounded text/JSON calls; credentials are never part of these DTOs."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Literal

from pydantic import Field, JsonValue

from .types import FrozenModel


class ModelRequest(FrozenModel):
    actor_id: str
    model: str = Field(min_length=1)
    reasoning_effort: str | None = None
    instructions: str
    input_json: str
    response_schema: dict[str, JsonValue]
    max_output_tokens: int = Field(gt=0)


class ModelResponse(FrozenModel):
    text: str
    model: str
    request_id: str | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)


class GatewayError(RuntimeError):
    """Sanitized category only; no credentials, request bodies, or provider error text."""


class ModelGateway(ABC):
    @property
    @abstractmethod
    def mode(self) -> Literal["fake", "live"]: ...

    @abstractmethod
    def complete(self, request: ModelRequest) -> ModelResponse: ...


class BoundedGateway(ModelGateway):
    """A fresh instance is owned by one job; no automatic transport retries."""

    def __init__(
        self,
        gateway: ModelGateway,
        max_calls: int = 8,
        max_output_tokens_per_call: int = 1200,
        max_request_chars: int = 100000,
        max_response_chars: int = 20000,
    ) -> None:
        if min(max_calls, max_output_tokens_per_call, max_request_chars, max_response_chars) <= 0:
            raise ValueError("Gateway budgets must be positive")
        self.gateway = gateway
        self.max_calls = max_calls
        self.max_output_tokens_per_call = max_output_tokens_per_call
        self.max_request_chars = max_request_chars
        self.max_response_chars = max_response_chars
        self.calls = 0

    @property
    def mode(self) -> Literal["fake", "live"]:
        return self.gateway.mode

    def complete(self, request: ModelRequest) -> ModelResponse:
        if self.calls >= self.max_calls:
            raise GatewayError("call_budget_exhausted")
        if request.max_output_tokens > self.max_output_tokens_per_call:
            raise GatewayError("output_budget_exceeded")
        if len(request.model_dump_json()) > self.max_request_chars:
            raise GatewayError("request_too_large")
        self.calls += 1
        response = self.gateway.complete(request.model_copy(deep=True))
        if len(response.text) > self.max_response_chars:
            raise GatewayError("response_too_large")
        return response


class FakeGateway(ModelGateway):
    """Callback sees the exact same bounded request contract as a live provider."""

    def __init__(self, respond: Callable[[ModelRequest], str]) -> None:
        self.respond = respond
        self.requests: list[ModelRequest] = []

    @property
    def mode(self) -> Literal["fake", "live"]:
        return "fake"

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request.model_copy(deep=True))
        return ModelResponse(
            text=self.respond(request), model=request.model, request_id=f"fake-{len(self.requests)}"
        )
