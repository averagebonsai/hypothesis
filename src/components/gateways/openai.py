"""Trusted Responses API transport. Credentials stay on this host-side object only."""

import json
from copy import deepcopy
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import JsonValue

from simulation_core.model_gateway import GatewayError, ModelGateway, ModelRequest, ModelResponse

from .settings import LiveModelSettings


def strict_schema(schema: dict[str, JsonValue]) -> dict[str, JsonValue]:
    result = deepcopy(schema)

    def visit(node: JsonValue) -> None:
        if not isinstance(node, dict):
            return
        node.pop("default", None)
        if "const" in node:
            node["enum"] = [node.pop("const")]
        if node.get("type") == "object":
            properties = node.get("properties")
            if not isinstance(properties, dict) or isinstance(
                node.get("additionalProperties"), dict
            ):
                raise GatewayError("unsupported_open_object_schema")
            node["required"] = list(properties)
            node["additionalProperties"] = False
        # Traverse schema nodes, not property maps: a field can itself be named 'default'.
        for key in ("properties", "$defs"):
            children = node.get(key)
            if isinstance(children, dict):
                for child in children.values():
                    visit(child)
        for key in ("items", "additionalProperties", "not"):
            visit(node.get(key))
        for key in ("anyOf", "oneOf", "allOf", "prefixItems"):
            children = node.get(key)
            if isinstance(children, list):
                for child in children:
                    visit(child)

    visit(result)
    return result


class OpenAIResponsesGateway(ModelGateway):
    endpoint = "https://api.openai.com/v1/responses"

    def __init__(
        self,
        api_key: str,
        allowed_models: frozenset[str],
        timeout: float = 45.0,
        max_response_bytes: int = 200000,
    ) -> None:
        if not api_key or not allowed_models or timeout <= 0 or max_response_bytes <= 0:
            raise ValueError(
                "Credentials, allowed models, and positive transport limits are required"
            )
        self._api_key = api_key
        self.allowed_models = allowed_models
        self.timeout = timeout
        self.max_response_bytes = max_response_bytes

    @classmethod
    def from_environment(cls, model: str) -> "OpenAIResponsesGateway":
        settings = LiveModelSettings.load(model)
        return cls(settings.api_key.get_secret_value(), frozenset({settings.model}))

    @property
    def mode(self) -> Literal["fake", "live"]:
        return "live"

    def complete(self, request: ModelRequest) -> ModelResponse:
        if request.model not in self.allowed_models:
            raise GatewayError("model_not_allowed")
        body = {
            "model": request.model,
            "instructions": request.instructions,
            "input": request.input_json,
            "max_output_tokens": request.max_output_tokens,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "actor_decision",
                    "schema": strict_schema(request.response_schema),
                    "strict": True,
                }
            },
        }
        if request.reasoning_effort is not None:
            body["reasoning"] = {"effort": request.reasoning_effort}
        http_request = Request(
            self.endpoint,
            data=json.dumps(body).encode(),
            method="POST",
            headers={
                "Authorization": "Bearer " + self._api_key,
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(http_request, timeout=self.timeout) as response:
                raw = response.read(self.max_response_bytes + 1)
        except HTTPError as exc:
            raise GatewayError(f"http_{exc.code}") from None
        except (URLError, TimeoutError, OSError):
            raise GatewayError("transport_error") from None
        if len(raw) > self.max_response_bytes:
            raise GatewayError("provider_response_too_large")
        try:
            data = json.loads(raw)
            if data.get("status") != "completed":
                raise GatewayError("provider_incomplete")
            texts = []
            for item in data.get("output", []):
                if item.get("type") == "message":
                    for part in item.get("content", []):
                        if part.get("type") == "refusal":
                            raise GatewayError("provider_refusal")
                        if part.get("type") == "output_text":
                            texts.append(part["text"])
            if not texts:
                raise GatewayError("provider_empty_output")
            usage = data.get("usage") or {}
            return ModelResponse(
                text="".join(texts),
                model=data.get("model", request.model),
                request_id=data.get("id"),
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
            )
        except (ValueError, KeyError, TypeError, AttributeError):
            raise GatewayError("invalid_provider_response") from None
