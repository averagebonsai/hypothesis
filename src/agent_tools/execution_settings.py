"""Operator-owned transport settings, resolved before scientific plans are frozen."""

from pydantic import Field

from simulation_core.policy_metadata import uses_llm_envelope
from simulation_core.types import FrozenModel, SimulationConfig


class ActorExecutionSettings(FrozenModel):
    model: str = Field(min_length=1)
    max_concurrency: int = Field(default=8, ge=1, le=32)
    provider_timeout_seconds: float = Field(default=180.0, gt=0)
    stream: bool = True
    reasoning_effort: str | None = None
    max_output_tokens: int | None = Field(default=None, gt=0)
    max_attempts: int = Field(default=2, gt=0, le=5)
    max_total_calls: int | None = Field(default=None, gt=0)
    max_calls_per_actor: int | None = Field(default=None, gt=0)

    def required_calls(self, config: SimulationConfig) -> dict[str, int]:
        """Use a static schedule or the runtime's one-action-per-actor-per-tick bound."""
        from itertools import islice

        from components.library import standard_registry

        counts = {actor.id: 0 for actor in config.world.actors if uses_llm_envelope(actor)}
        protocol = standard_registry().protocols.get(config.protocol_id)
        schedule = (
            protocol(config.protocol_parameters).decision_schedule(config.world)
            if protocol
            else None
        )
        if schedule is None:
            return {aid: config.max_steps * self.max_attempts for aid in counts}
        for phase in islice(schedule, config.max_steps):
            for actor_id in phase.actor_ids:
                if actor_id in counts:
                    counts[actor_id] += self.max_attempts
        return counts

    def call_budgets(self, config: SimulationConfig) -> tuple[int, dict[str, int]]:
        required = self.required_calls(config)
        per_actor = {
            aid: self.max_calls_per_actor or max(1, count) for aid, count in required.items()
        }
        return self.max_total_calls or max(1, sum(per_actor.values())), per_actor

    def validate_budget(self, config: SimulationConfig) -> None:
        counts = self.required_calls(config)
        total, per_actor = self.call_budgets(config)
        if sum(counts.values()) > total:
            raise ValueError(
                f"Actor call budget requires {sum(counts.values())} calls including retries; configured total is {total}"
            )
        if any(count > per_actor[aid] for aid, count in counts.items()):
            raise ValueError(
                "Per-actor call budget is insufficient for the declared schedule and retries"
            )

    def resolve(self, config: SimulationConfig) -> SimulationConfig:
        _, per_actor = self.call_budgets(config)
        actors = tuple(
            actor.model_copy(
                update={
                    "policy_parameters": {
                        **actor.policy_parameters,
                        "model": self.model,
                        "reasoning_effort": self.reasoning_effort,
                        "max_output_tokens": self.max_output_tokens,
                        "max_attempts": self.max_attempts,
                        "max_calls": per_actor[actor.id],
                    }
                }
            )
            if uses_llm_envelope(actor)
            else actor
            for actor in config.world.actors
        )
        return config.model_copy(
            update={"world": config.world.model_copy(update={"actors": actors})}
        )

    def capabilities(self) -> dict[str, object]:
        return {
            "live_actor_relay": True,
            "actor_execution": self.model_dump(mode="json"),
            "resolution": "Operator settings replace transport fields for llm.v1 and wrappers explicitly marked attributes.model_policy=llm.v1; scientific instructions/personas are preserved",
            "validation_network": "none",
            "live_acceptance": False,
        }
