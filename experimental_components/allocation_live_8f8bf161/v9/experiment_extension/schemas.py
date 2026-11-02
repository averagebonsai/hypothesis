from pydantic import BaseModel, Field, field_validator


class AllocationPayload(BaseModel):
    model_config = {"extra": "forbid"}
    allocation: tuple[float, ...] = Field(min_length=2)

    @field_validator("allocation", mode="before")
    @classmethod
    def _coerce_allocation(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("allocation", mode="after")
    @classmethod
    def _finite_allocation(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        from math import isfinite

        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and isfinite(float(v)) for v in value):
            raise ValueError("allocation entries must be finite numbers")
        return value
