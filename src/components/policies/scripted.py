from pydantic import Field, JsonValue

from simulation_core.policy import Policy
from simulation_core.types import Action, Decision, FrozenModel, Observation


class ScriptParameters(FrozenModel):
    kind: str
    payload: dict[str, JsonValue]
    memory_update: dict[str, JsonValue] | None = None
    private_updates: dict[str, JsonValue] = Field(default_factory=dict)
    required_fields: list[str] = Field(default_factory=list)


class ScriptedPolicy(Policy):
    def __init__(self, parameters: dict[str, JsonValue]):
        self.parameters = ScriptParameters.model_validate(parameters)

    def required_observation_fields(self) -> frozenset[str]:
        return frozenset(self.parameters.required_fields)

    def choose_action(self, observation: Observation) -> Decision:
        return Decision(
            rationale="Scripted policy: emit the configured action and payload.",
            action=Action(
                actor_id=observation.actor_id,
                kind=self.parameters.kind,
                payload=self.parameters.payload,
            ),
            memory_update=self.parameters.memory_update,
            private_updates=self.parameters.private_updates,
        ).model_copy(deep=True)
