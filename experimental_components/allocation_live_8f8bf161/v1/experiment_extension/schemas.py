from pydantic import BaseModel, Field

from simulation_core.types import FrozenModel


class AllocationPayload(FrozenModel):
    allocation: tuple[float, ...] = Field(min_length=2)
