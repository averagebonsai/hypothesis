"""Bid action payload for the sealed-bid second-price auction."""

from pydantic import Field

from simulation_core.types import FrozenModel


class BidPayload(FrozenModel):
    """One finite nonnegative sealed bid."""

    bid: float = Field(ge=0)
