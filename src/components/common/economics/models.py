"""Linear market demand, constant marginal costs, and exact lowest-price allocation."""

from collections.abc import Mapping
from math import isfinite
from typing import Self

from pydantic import Field, model_validator

from simulation_core.economics import (
    AllocationRule,
    CostModel,
    DemandModel,
    MarketAllocation,
    ProfitModel,
)
from simulation_core.types import FrozenModel


def nonnegative_finite(value: float) -> None:
    if not isfinite(value) or value < 0:
        raise ValueError("Expected a finite nonnegative value")


class LinearDemand(FrozenModel, DemandModel):
    a: float = Field(gt=0)
    b: float = Field(gt=0)

    @model_validator(mode="after")
    def finite_choke_price(self) -> Self:
        if not isfinite(self.a / self.b):
            raise ValueError("Demand choke price must be finite")
        return self

    @property
    def choke_price(self) -> float:
        return self.a / self.b

    def quantity(self, price: float) -> float:
        nonnegative_finite(price)
        return max(0.0, self.a - self.b * price)


class ConstantMarginalCost(FrozenModel, CostModel):
    marginal_cost: float = Field(ge=0)

    def total_cost(self, quantity: float) -> float:
        nonnegative_finite(quantity)
        value = self.marginal_cost * quantity
        if not isfinite(value):
            raise ValueError("Nonfinite cost")
        return value


class RevenueMinusCost(ProfitModel):
    def profit(self, price: float, quantity: float, costs: CostModel) -> float:
        nonnegative_finite(price)
        nonnegative_finite(quantity)
        value = price * quantity - costs.total_cost(quantity)
        if not isfinite(value):
            raise ValueError("Nonfinite profit")
        return value


class LowestPriceAllocation(AllocationRule):
    """Unlimited supply; exactly tied lowest prices share market demand equally."""

    def allocate(self, prices: Mapping[str, float], demand: DemandModel) -> MarketAllocation:
        if not prices:
            raise ValueError("At least one seller is required")
        for price in prices.values():
            nonnegative_finite(price)
        lowest = min(prices.values())
        winners = [aid for aid, price in prices.items() if price == lowest]
        quantity = demand.quantity(lowest)
        return MarketAllocation(
            market_price=lowest,
            total_quantity=quantity,
            quantities={aid: quantity / len(winners) if aid in winners else 0.0 for aid in prices},
        )
