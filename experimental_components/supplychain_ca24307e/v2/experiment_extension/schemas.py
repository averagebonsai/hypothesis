"""Typed contracts for the decentralized flood-response supply chain."""

from itertools import pairwise
from typing import Literal

from pydantic import Field, ValidationInfo, field_validator

from simulation_core.types import FrozenModel


class CapacityBlock(FrozenModel):
    start_day: int = Field(ge=1)
    end_day: int = Field(ge=1)
    capacity: int = Field(ge=0)


class SupplyChainParameters(FrozenModel):
    """World parameters: supplied economics plus explicit modeling conventions.

    Convention fields use single-value Literals so unsupported values are rejected
    with a clear error instead of silently changing behavior.
    """

    horizon_days: int = Field(ge=1, le=30)
    capacity_schedule: tuple[CapacityBlock, ...] = Field(min_length=1)
    initial_manufacturer_components: dict[str, int]
    initial_supplier_inventory: dict[str, int]
    supplier_daily_capacity: dict[str, int]
    manufacturer_daily_capacity: int = Field(ge=0)
    daily_demand: int = Field(ge=0)
    initial_finished_goods: int = Field(ge=0)
    transit_days: Literal[1]
    finished_selling_price: float = Field(ge=0)
    component_prices: dict[str, float]
    supplier_unit_production_cost: dict[str, float]
    assembly_unit_cost: float = Field(ge=0)
    transport_unit_charge: float = Field(ge=0)
    transport_unit_operating_cost: float = Field(ge=0)
    manufacturer_component_holding_unit_cost: float = Field(ge=0)
    supplier_holding_unit_cost: float = Field(ge=0)
    finished_goods_holding_unit_cost: float = Field(ge=0)
    quantity_unit: Literal["integer"] = "integer"
    order_policy: Literal["incremental_persistent"] = "incremental_persistent"
    unmet_demand_policy: Literal["lost_sales"] = "lost_sales"
    holding_cost_basis: Literal["closing_stock"] = "closing_stock"
    transfer_recognition: Literal["at_dispatch"] = "at_dispatch"
    opening_stock_cost: Literal["sunk"] = "sunk"
    priority_effect: Literal["advisory"] = "advisory"

    @field_validator("initial_manufacturer_components", "component_prices")
    @classmethod
    def _component_keys(cls, value: dict[str, object]) -> dict[str, object]:
        if set(value) != {"A", "B"}:
            raise ValueError("Component maps need exactly keys A and B")
        if any(
            not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount < 0
            for amount in value.values()
        ):
            raise ValueError("Component amounts must be nonnegative numbers")
        return value

    @field_validator(
        "initial_supplier_inventory", "supplier_daily_capacity", "supplier_unit_production_cost"
    )
    @classmethod
    def _supplier_keys(cls, value: dict[str, object]) -> dict[str, object]:
        if set(value) != {"supplier_a", "supplier_b"}:
            raise ValueError("Supplier maps need exactly keys supplier_a and supplier_b")
        if any(
            not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount < 0
            for amount in value.values()
        ):
            raise ValueError("Supplier amounts must be nonnegative numbers")
        return value

    @field_validator("capacity_schedule")
    @classmethod
    def _schedule_covers_horizon(
        cls, value: tuple[CapacityBlock, ...], info: ValidationInfo
    ) -> tuple[CapacityBlock, ...]:
        horizon = info.data.get("horizon_days", 9)
        blocks = list(value)
        if blocks[0].start_day != 1 or blocks[-1].end_day != horizon:
            raise ValueError("Capacity schedule must span days 1 through the horizon")
        for previous, current in pairwise(blocks):
            if current.start_day != previous.end_day + 1:
                raise ValueError("Capacity schedule blocks must be contiguous and ordered")
        for block in blocks:
            if block.end_day < block.start_day:
                raise ValueError("Capacity block end must not precede its start")
        return value


class OrderAction(FrozenModel):
    """Manufacturer ordering-phase payload: incremental orders plus advisory priorities."""

    order_a: int = Field(ge=0)
    order_b: int = Field(ge=0)
    priority_a: int = Field(ge=0)
    priority_b: int = Field(ge=0)


class ProduceAction(FrozenModel):
    """Manufacturer settlement-phase payload: finished units to assemble."""

    produce: int = Field(ge=0)


class SupplyAction(FrozenModel):
    """Supplier payload: produce, accept backlog, offer stock for shipment, priority."""

    produce: int = Field(ge=0)
    fulfill: int = Field(ge=0)
    ship_request: int = Field(ge=0)
    priority: int = Field(ge=0)


class AllocateAction(FrozenModel):
    """Logistics payload: capacity allocation across the two submitted offers."""

    allocate_a: int = Field(ge=0)
    allocate_b: int = Field(ge=0)
