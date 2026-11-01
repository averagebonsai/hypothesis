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
    """Joint demand quantities; particular models may add typed diagnostics."""

    quantities: dict[str, float]

    @model_validator(mode="after")
    def nonnegative_quantities(self) -> Self:
        if any(q < 0 for q in self.quantities.values()):
            raise ValueError("Demand quantities must be nonnegative")
        return self


class DemandSystem(ABC):
    """Joint prices map to demand for each differentiated product."""

    @abstractmethod
    def evaluate(self, prices: Mapping[str, float]) -> DemandSystemResult: ...


class DifferentiableDemandSystem(DemandSystem):
    @abstractmethod
    def own_price_derivatives(self, prices: Mapping[str, float]) -> dict[str, float]: ...


class InverseDemandModel(ABC):
    """Total supplied quantity determines the market-clearing price."""

    @abstractmethod
    def price(self, total_quantity: float) -> float: ...
