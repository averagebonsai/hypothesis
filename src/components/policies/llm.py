"""Generic schema-constrained actor policy; no economic equations or world access."""

import json
import logging
from functools import reduce
from operator import or_
from typing import Annotated, Literal

from pydantic import BaseModel, Field, JsonValue, StringConstraints, ValidationError, create_model

from simulation_core.model_gateway import GatewayError, ModelGateway, ModelRequest
from simulation_core.policy import Policy
from simulation_core.types import Action, Decision, FrozenModel, ModelCallRecord, Observation


class LLMParameters(FrozenModel):
    model: str = Field(min_length=1)
    instructions: str = Field(min_length=1)
    persona: str = ""
    reasoning_effort: str | None = None
    required_fields: list[str] = Field(default_factory=list)
    max_attempts: int = Field(default=2, gt=0, le=5)
    max_calls: int = Field(default=4, gt=0, le=100)
    max_output_tokens: int = Field(default=1000, gt=0, le=16000)


class JSONEntry(FrozenModel):
    key: str = Field(min_length=1)
    value_json: str = Field(max_length=4000)


class WireDecision(FrozenModel):
    action: Action
    # Entry lists allow generic JSON values without open-ended strict-provider schemas.
    memory_update: list[JSONEntry] | None
    private_updates: list[JSONEntry]
    rationale: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)
    ]


def entries(items: list[JSONEntry]) -> dict[str, JsonValue]:
    if len({item.key for item in items}) != len(items):
        raise ValueError("Duplicate update key")
    return {item.key: json.loads(item.value_json) for item in items}


class LLMPolicyError(RuntimeError):
    def __init__(self, records: tuple[ModelCallRecord, ...]) -> None:
        super().__init__("LLM decision failed within its configured budget")
        self.records = records


class LLMPolicy(Policy):
    def __init__(
        self,
        parameters: dict[str, JsonValue],
        gateway: ModelGateway,
        action_schemas: dict[str, type[BaseModel]] | None = None,
    ) -> None:
        self.parameters = LLMParameters.model_validate(parameters)
        self.gateway = gateway
        self.action_schemas = action_schemas or {}
        self.records: list[ModelCallRecord] = []

    def configure_action_schemas(self, schemas: dict[str, type[BaseModel]]) -> None:
        self.action_schemas = dict(schemas)

    def required_observation_fields(self) -> frozenset[str]:
        return frozenset(self.parameters.required_fields)

    def model_calls(self) -> tuple[ModelCallRecord, ...]:
        return tuple(record.model_copy(deep=True) for record in self.records)

    def response_model(self, observation: Observation) -> type[BaseModel]:
        variants = []
        for index, kind in enumerate(observation.allowed_action_kinds):
            schema = self.action_schemas[kind]
            variants.append(
                create_model(
                    f"ActionVariant{index}",
                    __base__=FrozenModel,
                    actor_id=(Literal.__getitem__(observation.actor_id), ...),  # type: ignore[arg-type]
                    # Literal types are constructed from validated actor-specific strings.
                    kind=(Literal.__getitem__(kind), ...),  # type: ignore[arg-type]
                    payload=(schema, ...),
                )
            )
        if not variants:
            raise ValueError("Actor has no action schemas")
        union = reduce(or_, variants)
        return create_model("ActorResponse", __base__=WireDecision, action=(union, ...))

    def choose_action(self, observation: Observation) -> Decision:
        response_model = self.response_model(observation)
        for attempt in range(1, self.parameters.max_attempts + 1):
            if len(self.records) >= self.parameters.max_calls:
                break
            request = ModelRequest(
                actor_id=observation.actor_id,
                model=self.parameters.model,
                reasoning_effort=self.parameters.reasoning_effort,
                instructions=(
                    "Act only as the assigned actor using the supplied observation. "
                    "Return one legal action. Do not invent hidden information. "
                    "Update only your own permitted private state. Every action MUST include a concise "
                    "decision rationale citing relevant observed facts, the objective, and any "
                    "assumptions about other actors. Do not claim knowledge of simultaneous "
                    "uncommitted choices. Provide a brief explanation, not internal reasoning. "
                    "Write simply, as if explaining to an undergraduate student."
                    "JSON update values are "
                    "encoded as value_json strings. " + self.parameters.instructions
                ),
                input_json=json.dumps(
                    {
                        "persona": self.parameters.persona,
                        "observation": observation.model_dump(mode="json"),
                        "retry": attempt > 1,
                    }
                ),
                response_schema=response_model.model_json_schema(),
                max_output_tokens=self.parameters.max_output_tokens,
            )
            response = None
            status: Literal["accepted", "invalid_response", "gateway_error"] = "gateway_error"
            error = None
            error_metadata: GatewayError | None = None
            decision = None
            try:
                response = self.gateway.complete(request)
                validated = response_model.model_validate_json(response.text)
                wire = WireDecision.model_validate(validated.model_dump())
                decision = Decision(
                    action=wire.action,
                    rationale=wire.rationale,
                    memory_update=None
                    if wire.memory_update is None
                    else entries(wire.memory_update),
                    private_updates=entries(wire.private_updates),
                )
                if set(decision.private_updates) - set(observation.writable_private_fields):
                    raise ValueError("Unauthorized private update")
                if decision.memory_update is not None and not observation.writable_memory:
                    raise ValueError("Unauthorized memory update")
                status = "accepted"
            except GatewayError as exc:
                error = str(exc)
                error_metadata = exc
            except (ValueError, ValidationError):
                decision = None
                status = "invalid_response"
                error = "schema_or_json_validation"
            self.records.append(
                ModelCallRecord(
                    actor_id=observation.actor_id,
                    attempt=attempt,
                    mode=self.gateway.mode,
                    model=self.parameters.model,
                    request=request.model_dump(mode="json"),
                    rationale=None if decision is None else decision.rationale,
                    response_model=None if response is None else response.model,
                    response_text=None if response is None else response.text,
                    request_id=(error_metadata.request_id if error_metadata else None)
                    if response is None
                    else response.request_id,
                    input_tokens=(error_metadata.input_tokens if error_metadata else 0)
                    if response is None
                    else response.input_tokens,
                    output_tokens=(error_metadata.output_tokens if error_metadata else 0)
                    if response is None
                    else response.output_tokens,
                    status=status,
                    error_category=error,
                )
            )
            if decision is not None:
                return decision
            logging.getLogger("simulation.actions").info(
                json.dumps(
                    {
                        "event": "policy_attempt_failed",
                        "actor_id": observation.actor_id,
                        "attempt": attempt,
                        "error_category": error,
                        "input_tokens": self.records[-1].input_tokens,
                        "output_tokens": self.records[-1].output_tokens,
                    }
                )
            )
        raise LLMPolicyError(self.model_calls())
