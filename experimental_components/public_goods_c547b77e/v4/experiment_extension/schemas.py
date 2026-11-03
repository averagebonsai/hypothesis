"""Contribution action payload for the public-goods mechanism."""

from pydantic import Field

from simulation_core.types import FrozenModel


class ContributionPayload(FrozenModel):
    """One scalar contribution to the shared pool.

    The static schema enforces nonnegativity so malformed actions fail inside the
    policy retry loop. The mechanism additionally enforces finiteness and the
    dynamic budget (contribution up to saved balance plus round endowment).
    """

    contribution: float = Field(ge=0)
