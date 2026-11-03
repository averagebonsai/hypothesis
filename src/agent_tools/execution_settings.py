"""Operator-owned transport settings, resolved before scientific plans are frozen."""

from pydantic import Field

from simulation_core.types import FrozenModel, SimulationConfig


class ActorExecutionSettings(FrozenModel):
    model: str = Field(min_length=1)
    max_concurrency: int = Field(default=8, ge=1, le=32)
    provider_timeout_seconds: float = Field(default=180.0, gt=0)
    stream: bool = True
    reasoning_effort: str | None = None
    max_output_tokens: int | None = Field(default=None, gt=0)
    max_attempts: int = Field(default=2, gt=0, le=5)
    max_total_calls: int = Field(default=48, gt=0)
    max_calls_per_actor: int = Field(default=48, gt=0, le=100)

    def validate_budget(self, config: SimulationConfig) -> None:
        """Check known schedules before provider calls, reserving configured retries."""
        from itertools import islice

        from components.library import standard_registry

        protocol = standard_registry().protocols.get(config.protocol_id)
        if protocol is None:
            return  # Custom protocols require a worker/domain-specific budget check.
        schedule = protocol(config.protocol_parameters).decision_schedule(config.world)
        if schedule is None:
            return
        counts = {actor.id: 0 for actor in config.world.actors if actor.policy_id == "llm.v1"}
        for phase in islice(schedule, config.max_steps):
            for actor_id in phase.actor_ids:
                if actor_id in counts:
                    counts[actor_id] += self.max_attempts
        if sum(counts.values()) > self.max_total_calls:
            raise ValueError(
                f"Actor call budget requires {sum(counts.values())} calls including retries; configured total is {self.max_total_calls}"
            )
        if any(count > self.max_calls_per_actor for count in counts.values()):
            raise ValueError(
                "Per-actor call budget is insufficient for the declared schedule and retries"
            )

    def resolve(self, config: SimulationConfig) -> SimulationConfig:
        actors = tuple(
            actor.model_copy(
                update={
                    "policy_parameters": {
                        **actor.policy_parameters,
                        "model": self.model,
                        "reasoning_effort": self.reasoning_effort,
                        "max_output_tokens": self.max_output_tokens,
                        "max_attempts": self.max_attempts,
                        "max_calls": self.max_calls_per_actor,
                    }
                }
            )
            if actor.policy_id == "llm.v1"
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
            "resolution": "Operator settings replace generated llm.v1 transport fields before plan freeze; scientific instructions/personas are preserved",
            "validation_network": "none",
            "live_acceptance": False,
        }
