"""Stable segmented multinomial logit including an explicit outside option."""

from collections.abc import Mapping
from math import exp, fsum, isclose, isfinite
from typing import Self

from pydantic import Field, model_validator

from components.common.economics.models import nonnegative_finite
from simulation_core.economics import DemandSystemResult, DifferentiableDemandSystem
from simulation_core.types import FrozenModel


class SegmentedDemandResult(DemandSystemResult):
    segment_shares: dict[str, dict[str, float]]
    outside_shares: dict[str, float]
    outside_quantity: float = Field(ge=0)
    total_population: float = Field(gt=0)

    @model_validator(mode="after")
    def conservation(self) -> Self:
        if set(self.segment_shares) != set(self.outside_shares):
            raise ValueError("Every segment requires an outside share")
        for sid, shares in self.segment_shares.items():
            values = [*shares.values(), self.outside_shares[sid]]
            if set(shares) != set(self.quantities) or any(not 0 <= value <= 1 for value in values):
                raise ValueError("Invalid segment share dimensions or probabilities")
            if not isclose(sum(values), 1.0, abs_tol=1e-12):
                raise ValueError("Firm plus outside shares must sum to one")
        if not isclose(
            sum(self.quantities.values()) + self.outside_quantity,
            self.total_population,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValueError("Firm and outside quantities must conserve population")
        return self


class ConsumerSegment(FrozenModel):
    id: str = Field(min_length=1)
    population: float = Field(gt=0)
    price_sensitivity: float = Field(gt=0)
    utilities: dict[str, float] = Field(min_length=1)
    outside_utility: float = 0.0


class SegmentedLogitDemand(FrozenModel, DifferentiableDemandSystem):
    firm_ids: tuple[str, ...] = Field(min_length=1)
    segments: tuple[ConsumerSegment, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def dimensions(self) -> Self:
        if len(set(self.firm_ids)) != len(self.firm_ids) or any(not aid for aid in self.firm_ids):
            raise ValueError("Firm IDs must be unique and nonempty")
        if len({segment.id for segment in self.segments}) != len(self.segments):
            raise ValueError("Segment IDs must be unique")
        if any(set(segment.utilities) != set(self.firm_ids) for segment in self.segments):
            raise ValueError("Every segment needs exactly one utility per firm")
        try:
            total = fsum(segment.population for segment in self.segments)
        except OverflowError:
            raise ValueError("Total population must be finite") from None
        if not isfinite(total):
            raise ValueError("Total population must be finite")
        return self

    def evaluate(self, prices: Mapping[str, float]) -> SegmentedDemandResult:
        if set(prices) != set(self.firm_ids):
            raise ValueError("Prices must cover exactly the demand-system firms")
        for price in prices.values():
            nonnegative_finite(price)
        quantities = {aid: 0.0 for aid in self.firm_ids}
        shares = {}
        outside = {}
        outside_quantity = 0.0
        for segment in self.segments:
            scores = [
                segment.outside_utility,
                *(
                    segment.utilities[aid] - segment.price_sensitivity * prices[aid]
                    for aid in self.firm_ids
                ),
            ]
            offset = max(scores)  # Includes a finite outside utility, even when products underflow.
            weights = [exp(score - offset) for score in scores]
            denominator = fsum(weights)
            probabilities = [value / denominator for value in weights]
            outside[segment.id] = probabilities[0]
            shares[segment.id] = {aid: probabilities[i + 1] for i, aid in enumerate(self.firm_ids)}
            for aid in self.firm_ids:
                quantities[aid] += segment.population * shares[segment.id][aid]
            outside_quantity += segment.population * probabilities[0]
        return SegmentedDemandResult(
            quantities=quantities,
            segment_shares=shares,
            outside_shares=outside,
            outside_quantity=outside_quantity,
            total_population=fsum(s.population for s in self.segments),
        )

    def own_price_derivatives(self, prices: Mapping[str, float]) -> dict[str, float]:
        result = self.evaluate(prices)
        return {
            aid: -fsum(
                segment.population
                * segment.price_sensitivity
                * result.segment_shares[segment.id][aid]
                * (1 - result.segment_shares[segment.id][aid])
                for segment in self.segments
            )
            for aid in self.firm_ids
        }
