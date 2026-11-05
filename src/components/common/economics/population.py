"""Population segmentation and aggregate choice models for representative agents."""

from collections.abc import Mapping
from math import exp, isfinite
from typing import Self

from pydantic import Field, model_validator

from simulation_core.types import FrozenModel


class ConstituentSegment(FrozenModel):
    """A population demographic segment with discrete preferences and price sensitivity."""

    id: str
    population: float = Field(gt=0)
    base_utilities: dict[str, float] = Field(default_factory=dict)
    price_sensitivity: float = Field(default=1.0, gt=0)
    outside_utility: float = 0.0

    @model_validator(mode="after")
    def validate_finite(self) -> Self:
        if not isfinite(self.population):
            raise ValueError("Population must be finite")
        if not isfinite(self.price_sensitivity):
            raise ValueError("Price sensitivity must be finite")
        if not isfinite(self.outside_utility):
            raise ValueError("Outside utility must be finite")
        for k, v in self.base_utilities.items():
            if not isfinite(v):
                raise ValueError(f"Base utility for {k} must be finite")
        return self


class PopulationSystem(FrozenModel):
    """Aggregate population system composed of constituent preference segments."""

    segments: tuple[ConstituentSegment, ...] = Field(default_factory=tuple)

    @property
    def total_population(self) -> float:
        return sum(seg.population for seg in self.segments)

    def segment_shares(
        self, prices: Mapping[str, float]
    ) -> dict[str, dict[str, float]]:
        """Compute choice shares per segment using numerical-stable multinomial logit."""
        shares_by_segment: dict[str, dict[str, float]] = {}
        for seg in self.segments:
            utilities: dict[str, float] = {}
            for opt, price in prices.items():
                base = seg.base_utilities.get(opt, 0.0)
                utilities[opt] = base - seg.price_sensitivity * price
            utilities["outside"] = seg.outside_utility

            # Numerical stability: subtract max utility
            max_u = max(utilities.values())
            exp_u = {opt: exp(u - max_u) for opt, u in utilities.items()}
            sum_exp = sum(exp_u.values())

            shares_by_segment[seg.id] = {opt: val / sum_exp for opt, val in exp_u.items()}
        return shares_by_segment

    def aggregate_demand(self, prices: Mapping[str, float]) -> dict[str, float]:
        """Aggregate demands across all segments; conserves total population."""
        segment_shares = self.segment_shares(prices)
        total_demand: dict[str, float] = {opt: 0.0 for opt in prices}
        total_demand["outside"] = 0.0

        for seg in self.segments:
            shares = segment_shares[seg.id]
            for opt, share in shares.items():
                total_demand[opt] = total_demand.get(opt, 0.0) + seg.population * share

        return total_demand
