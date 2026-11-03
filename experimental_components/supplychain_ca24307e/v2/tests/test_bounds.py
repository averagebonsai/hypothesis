"""Physical sales bound: hand-derived values and parameter variation."""

from experiment_extension.bounds import physical_bounds
from experiment_extension.mechanism import capacity_for_day
from experiment_extension.schemas import SupplyChainParameters
from helpers import draft_data, run_offline


def _params() -> dict:
    data = draft_data()["simulation"]
    assert isinstance(data, dict)
    world = data["world"]
    assert isinstance(world, dict)
    parameters = world["parameters"]
    assert isinstance(parameters, dict)
    return dict(parameters)


def test_hand_derived_overall_bound() -> None:
    bounds = physical_bounds(_params())
    assert bounds.horizon_days == 9
    assert bounds.total_demand == 720
    assert bounds.assembly_total == 900
    assert bounds.transport_units_total == 400 + 320 + 600
    # Only days 1-8 dispatches arrive in time: 400 + 320 + 400 = 1120.
    assert bounds.usable_transport_units == 1120
    # (150 + 150 + 1120) // 2 = 710 balanced pairs at most.
    assert bounds.pair_bound == 710
    assert bounds.overall_sales_bound == 710
    assert bounds.minimum_lost_sales == 10
    assert "710" in bounds.derivation
    assert "optimistic physical upper bound" in bounds.derivation
    assert "equilibrium benchmark" in bounds.derivation
    params = SupplyChainParameters.from_json_values(_params())
    assert capacity_for_day(params, 3) == 80
    assert capacity_for_day(params, 7) == 200


def test_bound_without_disruption() -> None:
    parameters = _params()
    parameters["capacity_schedule"] = [{"start_day": 1, "end_day": 9, "capacity": 200}]
    bounds = physical_bounds(parameters)
    assert bounds.usable_transport_units == 1600
    assert bounds.pair_bound == (300 + 1600) // 2 == 950
    assert bounds.overall_sales_bound == 720
    assert bounds.minimum_lost_sales == 0


def test_bound_tightens_with_small_opening_stock() -> None:
    parameters = _params()
    parameters["initial_manufacturer_components"] = {"A": 0, "B": 0}
    bounds = physical_bounds(parameters)
    assert bounds.pair_bound == 1120 // 2 == 560
    assert bounds.overall_sales_bound == 560
    assert bounds.minimum_lost_sales == 160


def test_bound_follows_demand_and_assembly() -> None:
    parameters = _params()
    parameters["daily_demand"] = 10
    bounds = physical_bounds(parameters)
    assert bounds.total_demand == 90
    assert bounds.overall_sales_bound == 90
    parameters = _params()
    parameters["manufacturer_daily_capacity"] = 10
    bounds = physical_bounds(parameters)
    assert bounds.assembly_total == 90
    assert bounds.overall_sales_bound == 90


def test_reported_sales_never_exceed_bound() -> None:
    from experiment_extension.metrics import daily_records

    artifact = run_offline("baseline")
    bounds = physical_bounds(_params())
    sold = sum(record.sold for record in daily_records(artifact))
    assert sold <= bounds.overall_sales_bound
    assert sold == 630
