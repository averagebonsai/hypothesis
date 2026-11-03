"""LLM policy wrapper with observation-only legality checks and exact fallback.

The wrapper delegates every model call to :class:`LLMPolicy` with the canonical
observation packet, adds contextual payload validation derived only from the
permitted observation, and returns an explicitly configured zero-action
fallback after the attempt budget is exhausted. Fallback decisions carry no
private or memory writes, so they never conflict with mechanism-owned updates.
"""

from copy import deepcopy
from typing import Self

from pydantic import BaseModel, JsonValue, model_validator

from components.policies.llm import LLMParameters, LLMPolicy, LLMPolicyError
from simulation_core.model_gateway import ModelGateway
from simulation_core.types import Action, Decision, FrozenModel, Observation

FALLBACK_KIND_BY_STAGE = {
    "order": "order",
    "supply": "supply",
    "ship": "allocate",
    "settle": "produce",
}


class SupplyChainPolicyParameters(LLMParameters):
    """LLM transport fields plus the exact per-kind fallback payload map."""

    fallback: dict[str, dict[str, JsonValue]]


def _integer(payload: dict[str, JsonValue], field: str) -> int:
    value = payload.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"Payload field {field} must be an integer")  # noqa: TRY004 - retry loop maps ValueError to invalid_response
    return value


def _fact(observation: Observation, field: str) -> int:
    value = observation.private.facts.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"Observation lacks integer private fact {field}")  # noqa: TRY004 - retry loop maps ValueError to invalid_response
    return value


def _visible(observation: Observation, field: str) -> int:
    value = observation.visible.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"Observation lacks integer visible field {field}")  # noqa: TRY004 - retry loop maps ValueError to invalid_response
    return value


class SupplyChainPolicy(LLMPolicy):
    """Contextual validation plus exhausted-attempt zero-action fallback."""

    def __init__(
        self, parameters: dict[str, JsonValue], gateway: ModelGateway | None = None
    ) -> None:
        validated = SupplyChainPolicyParameters.from_json_values(parameters)
        if gateway is None:  # Live relay binding; tests inject a fake gateway.
            from extension_worker.actor_relay import RelayGateway

            gateway = RelayGateway()
        base = validated.model_dump(mode="json")
        fallback = base.pop("fallback")
        super().__init__(base, gateway)
        self.fallback_map: dict[str, dict[str, JsonValue]] = fallback
        self.fallback_count = 0
        self.infeasible_proposals: list[dict[str, JsonValue]] = []

    def response_model(self, observation: Observation) -> type[BaseModel]:
        base = super().response_model(observation)
        checker = self
        snapshot = observation.model_copy(deep=True)

        class ContextualResponse(base):  # type: ignore[misc, valid-type]
            @model_validator(mode="after")
            def check_context(self) -> Self:
                checker.check_action(snapshot, self.action)
                return self

        ContextualResponse.__name__ = "ContextualActorResponse"
        return ContextualResponse

    def check_action(self, observation: Observation, action: Action) -> None:
        """Mirror mechanism legality using only the permitted observation."""
        raw_payload = action.payload
        payload = (
            raw_payload if isinstance(raw_payload, dict) else raw_payload.model_dump(mode="json")
        )
        try:
            if action.kind == "order":
                self._check_order(payload)
            elif action.kind == "produce":
                self._check_produce(observation, payload)
            elif action.kind == "supply":
                self._check_supply(observation, payload)
            elif action.kind == "allocate":
                self._check_allocate(observation, payload)
            else:
                raise ValueError(f"Unknown action kind: {action.kind}")
        except ValueError as exc:
            self.infeasible_proposals.append(
                {
                    "actor_id": observation.actor_id,
                    "kind": action.kind,
                    "payload": dict(payload),
                    "reason": str(exc),
                }
            )
            raise

    def _check_order(self, payload: dict[str, JsonValue]) -> None:
        for field in ("order_a", "order_b", "priority_a", "priority_b"):
            _integer(payload, field)

    def _check_produce(self, observation: Observation, payload: dict[str, JsonValue]) -> None:
        quantity = _integer(payload, "produce")
        limit = min(
            _fact(observation, "comp_a"),
            _fact(observation, "comp_b"),
            _fact(observation, "capacity"),
        )
        if quantity > limit:
            raise ValueError(f"Production {quantity} exceeds feasible {limit}")

    def _check_supply(self, observation: Observation, payload: dict[str, JsonValue]) -> None:
        produce = _integer(payload, "produce")
        fulfill = _integer(payload, "fulfill")
        ship_request = _integer(payload, "ship_request")
        _integer(payload, "priority")
        capacity = _fact(observation, "capacity")
        backlog = _fact(observation, "backlog")
        inventory = _fact(observation, "inventory")
        if produce > capacity:
            raise ValueError(f"Production {produce} exceeds capacity {capacity}")
        if fulfill > backlog:
            raise ValueError(f"Acceptance {fulfill} exceeds backlog {backlog}")
        if ship_request > inventory + produce:
            raise ValueError(f"Offer {ship_request} exceeds available stock {inventory + produce}")

    def _check_allocate(self, observation: Observation, payload: dict[str, JsonValue]) -> None:
        allocate_a = _integer(payload, "allocate_a")
        allocate_b = _integer(payload, "allocate_b")
        offer_a = _visible(observation, "offer_a")
        offer_b = _visible(observation, "offer_b")
        capacity = _visible(observation, "capacity")
        if allocate_a > offer_a:
            raise ValueError(f"Allocation {allocate_a} exceeds offer {offer_a} for A")
        if allocate_b > offer_b:
            raise ValueError(f"Allocation {allocate_b} exceeds offer {offer_b} for B")
        if allocate_a + allocate_b > capacity:
            raise ValueError(f"Allocation {allocate_a + allocate_b} exceeds capacity {capacity}")

    def choose_action(self, observation: Observation) -> Decision:
        try:
            return super().choose_action(observation)
        except LLMPolicyError:
            stage = observation.phase.rsplit("_", 1)[-1]
            kind = FALLBACK_KIND_BY_STAGE.get(stage)
            if (
                kind is None
                or kind not in observation.allowed_action_kinds
                or kind not in self.fallback_map
            ):
                raise
            self.fallback_count += 1
            attempts = self.parameters.max_attempts
            return Decision(
                action=Action(
                    actor_id=observation.actor_id,
                    kind=kind,
                    payload=deepcopy(self.fallback_map[kind]),
                ),
                rationale=(
                    f"Safe fallback after {attempts} exhausted attempts: no valid model "
                    f"response was accepted, so this phase records the configured zero "
                    f"action for kind '{kind}'."
                ),
                memory_update=None,
                private_updates={},
            ).model_copy(deep=True)


class FallbackSummary(FrozenModel):
    """Test-visible instrumentation for fallback behavior."""

    fallback_count: int
    infeasible_proposals: int
