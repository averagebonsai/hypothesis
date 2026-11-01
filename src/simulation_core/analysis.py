"""Shared envelope for typed mathematical or domain-specific analysis results."""

from pydantic import Field, JsonValue

from .types import FrozenModel


class AnalysisResult(FrozenModel):
    """Common result envelope; domain analyses define their own typed result fields."""

    status: str
    certification: str | None = None
    diagnostics: dict[str, JsonValue] = Field(default_factory=dict)
