"""Small domain contracts shared by schemas and numerical tools."""

from typing import Self

from pydantic import model_validator

from .types import FrozenModel


class ScalarInterval(FrozenModel):
    lower: float
    upper: float

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.lower >= self.upper:
            raise ValueError("Scalar interval requires lower < upper")
        return self

    def contains(self, value: float) -> bool:
        return self.lower <= value <= self.upper
