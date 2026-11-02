from pydantic import BaseModel, Field, field_validator


class AllocationPayload(BaseModel):
    model_config = {"extra": "forbid"}
    allocation: tuple[float, ...] = Field(min_length=2)

    @field_validator("allocation", mode="before")
    @classmethod
    def _coerce_allocation(cls, value: object) -> object:
        if isinstance(list, type) and isinstance(value, list):  # placeholder
            return tuple(value)
        return value
