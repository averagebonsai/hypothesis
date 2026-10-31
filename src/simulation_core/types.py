"""JSON boundary models. Nested values are isolated with deep snapshots at runtime."""

import json
from math import isfinite
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    @classmethod
    def from_json_values(cls, value: JsonValue) -> Self:
        """Validate JSON transport values as JSON, including tuple-backed array schemas."""
        return cls.model_validate_json(json.dumps(value, allow_nan=False))

    @model_validator(mode="after")
    def finite_json(self) -> Self:
        def check(value: object) -> None:
            if isinstance(value, float) and not isfinite(value):
                raise ValueError("Nonfinite numbers are forbidden")
            if isinstance(value, dict):
                for item in value.values():
                    check(item)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    check(item)

        check(self.model_dump())
        return self


class ActionSpace(FrozenModel):
    schemas: dict[str, str] = Field(min_length=1)


class Actor(FrozenModel):
    id: str = Field(min_length=1)
    kind: str
    attributes: dict[str, JsonValue] = Field(default_factory=dict)
    action_space: ActionSpace
    policy_id: str
    policy_parameters: dict[str, JsonValue] = Field(default_factory=dict)


class Action(FrozenModel):
    actor_id: str
    kind: str
    payload: dict[str, JsonValue] = Field(default_factory=dict)


class PrivateState(FrozenModel):
    facts: dict[str, JsonValue] = Field(default_factory=dict)
    memory: dict[str, JsonValue] = Field(default_factory=dict)


class WorldConfig(FrozenModel):
    actors: tuple[Actor, ...] = Field(min_length=1)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    initial_public_state: dict[str, JsonValue] = Field(default_factory=dict)
    initial_private_state: dict[str, PrivateState] = Field(default_factory=dict)

    @model_validator(mode="after")
    def references(self) -> Self:
        ids = [actor.id for actor in self.actors]
        if len(ids) != len(set(ids)):
            raise ValueError("Actor IDs must be unique")
        if set(self.initial_private_state) - set(ids):
            raise ValueError("Unknown actor in private state")
        return self


class WorldState(FrozenModel):
    tick: int = Field(ge=0)
    phase: str
    public: dict[str, JsonValue] = Field(default_factory=dict)
    private: dict[str, PrivateState] = Field(default_factory=dict)


class Observation(FrozenModel):
    actor_id: str
    phase: str
    visible: dict[str, JsonValue]
    private: PrivateState
    allowed_action_kinds: tuple[str, ...]
    writable_private_fields: tuple[str, ...] = ()
    writable_memory: bool = True


class ObservationPermissions(FrozenModel):
    """Top-level allowlists; nested contents of an allowed field are visible."""

    public_fields: tuple[str, ...] = ()
    private_fields: tuple[str, ...] = ()
    readable_memory: bool = True
    writable_private_fields: tuple[str, ...] = ()
    writable_memory: bool = True


class Decision(FrozenModel):
    action: Action
    rationale: str | None = Field(default=None, min_length=1, max_length=600)
    # Replaces this actor's memory when provided; cannot address another actor.
    memory_update: dict[str, JsonValue] | None = None
    private_updates: dict[str, JsonValue] = Field(default_factory=dict)


class Outcome(FrozenModel):
    payoffs: dict[str, float] = Field(default_factory=dict)
    metrics: dict[str, JsonValue] = Field(default_factory=dict)


class TransitionResult(FrozenModel):
    # Domain changes only: protocol/runtime own tick and phase.
    public: dict[str, JsonValue]
    outcome: Outcome = Field(default_factory=Outcome)
    private_updates: dict[str, PrivateState] = Field(default_factory=dict)


class Assumption(FrozenModel):
    path: str
    value: JsonValue
    source: Literal["user", "textbook", "model", "default"]
    rationale: str = Field(min_length=1)
    reference: str | None = None

    @field_validator("path")
    @classmethod
    def valid_path(cls, value: str) -> str:
        from .provenance import pointer_tokens

        tokens = pointer_tokens(value)
        if tokens[0] == "assumptions":
            raise ValueError("Assumptions must refer to execution fields")
        return value


class BenchmarkSpec(FrozenModel):
    solver_id: str
    game_view_id: str
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    information_assumption: Literal["complete_information"] = "complete_information"
    comparison_tick: int | None = Field(default=None, ge=1)


class ModelCallRecord(FrozenModel):
    actor_id: str
    attempt: int = Field(ge=1)
    mode: Literal["fake", "live"]
    model: str
    request: dict[str, JsonValue]
    rationale: str | None = None
    response_model: str | None = None
    response_text: str | None = None
    request_id: str | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    status: Literal["accepted", "invalid_response", "gateway_error"]
    error_category: str | None = None


class SimulationConfig(FrozenModel):
    schema_version: Literal["simulation.config.v1"] = "simulation.config.v1"
    world: WorldConfig
    mechanism_id: str
    protocol_id: str
    protocol_parameters: dict[str, JsonValue] = Field(default_factory=dict)
    permissions: dict[str, ObservationPermissions] = Field(default_factory=dict)
    benchmark: BenchmarkSpec | None = None
    max_steps: int = Field(default=100, gt=0)
    assumptions: tuple[Assumption, ...] = ()

    @model_validator(mode="after")
    def permission_references(self) -> Self:
        if set(self.permissions) - {actor.id for actor in self.world.actors}:
            raise ValueError("Unknown actor in permissions")
        from .provenance import resolve_pointer, same_json

        paths = [assumption.path for assumption in self.assumptions]
        if len(set(paths)) != len(paths):
            raise ValueError("Duplicate assumption path")
        for assumption in self.assumptions:
            if not same_json(
                resolve_pointer(self.model_dump(mode="json"), assumption.path), assumption.value
            ):
                raise ValueError(
                    f"Assumption differs from resolved configuration: {assumption.path}"
                )
        return self


class Event(FrozenModel):
    schema_version: Literal["simulation.event.v1"] = "simulation.event.v1"
    sequence: int = Field(ge=0)
    kind: Literal["initialized", "committed"]
    state: WorldState
    actions: tuple[Action, ...] = ()
    decisions: tuple[Decision, ...] = ()
    outcome: Outcome | None = None
    model_calls: tuple[ModelCallRecord, ...] = ()


class RunResult(FrozenModel):
    status: Literal["completed", "step_limit"]
    final_state: WorldState
    outcomes: tuple[Outcome, ...]
    events: tuple[Event, ...]
    assumptions: tuple[Assumption, ...]
    component_ids: tuple[str, ...]
    model_calls: tuple[ModelCallRecord, ...] = ()
