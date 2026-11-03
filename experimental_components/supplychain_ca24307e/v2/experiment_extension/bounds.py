"""Action-independent physical sales bound for the flood scenario.

Every sold unit consumes one Component A and one Component B. Components usable
for production within the horizon are the manufacturer's opening stock plus
shipments dispatched early enough to arrive before the final day. This module
derives that bound from parameters alone; it never calls the mechanism, so it
is an independent mathematical reference rather than a second simulation.
"""

from experiment_extension.mechanism import capacity_for_day
from experiment_extension.schemas import SupplyChainParameters
from pydantic import JsonValue

from simulation_core.types import FrozenModel


class PhysicalBounds(FrozenModel):
    horizon_days: int
    total_demand: int
    assembly_total: int
    transport_units_total: int
    usable_transport_units: int
    pair_bound: int
    overall_sales_bound: int
    minimum_lost_sales: int
    derivation: str


def physical_bounds(parameters: dict[str, JsonValue]) -> PhysicalBounds:
    params = SupplyChainParameters.from_json_values(parameters)
    horizon = params.horizon_days
    total_demand = horizon * params.daily_demand
    assembly_total = horizon * params.manufacturer_daily_capacity
    transport_units_total = sum(capacity_for_day(params, day) for day in range(1, horizon + 1))
    # Day-horizon dispatches arrive after the horizon, so only days 1..h-1 feed
    # production. Each additional finished unit needs one A and one B arrival.
    usable_transport_units = sum(capacity_for_day(params, day) for day in range(1, horizon))
    opening_pairs = (
        params.initial_manufacturer_components["A"] + params.initial_manufacturer_components["B"]
    )
    pair_bound = (opening_pairs + usable_transport_units) // 2
    overall = min(total_demand, assembly_total, pair_bound)
    minimum_lost = max(0, total_demand - overall)
    derivation = (
        f"Total customer demand is {horizon} days x {params.daily_demand} = {total_demand} units. "
        f"Assembly capacity allows {horizon} x {params.manufacturer_daily_capacity} = {assembly_total}. "
        f"Transport offers {transport_units_total} component units, but only {usable_transport_units} "
        f"dispatched on days 1-{max(horizon - 1, 1)} can arrive in time for production. With "
        f"{opening_pairs} opening components, at most ({opening_pairs}+{usable_transport_units})//2 = "
        f"{pair_bound} finished units can ever be assembled. Hence total sales over the horizon cannot "
        f"exceed min({total_demand}, {assembly_total}, {pair_bound}) = {overall}. This {overall} is an "
        f"optimistic physical upper bound, not an attainable plan or equilibrium benchmark: it assumes "
        f"perfectly balanced A/B arrivals and ignores day-by-day stockouts, so observed sales can fall "
        f"well short of it, while at least {minimum_lost} of the {total_demand} demanded units are "
        f"unavoidably lost no matter how the actors play."
    )
    return PhysicalBounds(
        horizon_days=horizon,
        total_demand=total_demand,
        assembly_total=assembly_total,
        transport_units_total=transport_units_total,
        usable_transport_units=usable_transport_units,
        pair_bound=pair_bound,
        overall_sales_bound=overall,
        minimum_lost_sales=minimum_lost,
        derivation=derivation,
    )
