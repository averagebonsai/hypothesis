"""Composable economic primitives, independent of actors, protocols, and policy choice."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from math import isclose
from typing import Self

from pydantic import Field, model_validator

from .types import FrozenModel


class DemandModel(ABC):
    """Aggregate demand at a single market price (not a differentiated-demand system)."""

    @abstractmethod
    def quantity(self, price: float) -> float: ...


class CostModel(ABC):
    @abstractmethod
    def total_cost(self, quantity: float) -> float: ...


class ProfitModel(ABC):
    @abstractmethod
    def profit(self, price: float, quantity: float, costs: CostModel) -> float: ...


class MarketAllocation(FrozenModel):
    market_price: float = Field(ge=0)
    total_quantity: float = Field(ge=0)
    quantities: dict[str, float]

    @model_validator(mode="after")
    def allocation_conserves_quantity(self) -> Self:
        if any(quantity < 0 for quantity in self.quantities.values()):
            raise ValueError("Allocated quantities cannot be negative")
        if not isclose(
            sum(self.quantities.values()), self.total_quantity, rel_tol=1e-12, abs_tol=1e-12
        ):
            raise ValueError("Allocated quantities must sum to total quantity")
        return self


class AllocationRule(ABC):
    @abstractmethod
    def allocate(self, prices: Mapping[str, float], demand: DemandModel) -> MarketAllocation: ...


class DemandSystemResult(FrozenModel):
    quantities: dict[str, float]
    segment_shares: dict[str, dict[str, float]]
    outside_shares: dict[str, float]
    outside_quantity: float = Field(ge=0)
    total_population: float = Field(gt=0)

    @model_validator(mode="after")
    def conservation(self) -> Self:
        if any(q < 0 for q in self.quantities.values()):
            raise ValueError("Demand quantities must be nonnegative")
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


class DemandSystem(ABC):
    """Joint prices map to demand for each differentiated product."""

    @abstractmethod
    def evaluate(self, prices: Mapping[str, float]) -> DemandSystemResult: ...


class DifferentiableDemandSystem(DemandSystem):
    @abstractmethod
    def own_price_derivatives(self, prices: Mapping[str, float]) -> dict[str, float]: ...
