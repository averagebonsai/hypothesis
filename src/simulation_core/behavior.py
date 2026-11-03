"""Typed scientific instructions, distinct from operator model/transport settings."""

from pydantic import Field

from .types import FrozenModel


class ActorBehaviorSpec(FrozenModel):
    actor_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    behavioral_instructions: str = ""
    background: str = ""

    def prompt(self) -> str:
        return (
            f"Assigned actor: {self.actor_id}.\nObjective: {self.objective}\n"
            f"Behavioral instructions: {self.behavioral_instructions}\n"
            f"Background: {self.background}\n"
            "Other actors' private instructions are not supplied. Base beliefs about them on "
            "permitted observations and distinguish beliefs from observed facts. "
            "They do not override action legality, information access or response requirements."
        )
