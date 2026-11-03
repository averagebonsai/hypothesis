"""Every supplied parameter is load-bearing; unsupported values are rejected."""

import pytest
from experiment_extension.mechanism import SupplyChainMechanism
from experiment_extension.schemas import SupplyChainParameters
from helpers import (
    draft_data,
    draft_simulation,
    experiment_request,
    offline_simulation,
    run_offline,
    step_day,
)
from helpers import mechanism_and_state as _base_setup

from simulation_core.execution import JobManifest, JobRunner, LocalBackend
from simulation_core.types import SimulationConfig, WorldState

ORDER = {"order_a": 80, "order_b": 80, "priority_a": 0, "priority_b": 0}
SUPPLY = {"produce": 80, "fulfill": 80, "ship_request": 80, "priority": 0}
ALLOCATE = {"allocate_a": 80, "allocate_b": 80}
PRODUCE = {"produce": 80}


def mechanism_and_state() -> tuple[SupplyChainMechanism, SimulationConfig, WorldState]:
    """Local setup: helper fixture plus draft-config validation through a fresh mechanism."""
    mechanism, config, state = _base_setup()
    assert SupplyChainMechanism().validate_config(config.world) is None
    return mechanism, config, state


def _variant(parameters: dict) -> SimulationConfig:
    data = draft_data()["simulation"]
    assert isinstance(data, dict)
    data = dict(data)
    world = dict(data["world"])
    world["parameters"] = parameters
    data["world"] = world
    data["assumptions"] = []
    return SimulationConfig.from_json_values(data)


def _day_one_profits(overrides: dict) -> dict[str, float]:
    base = draft_data()["simulation"]
    assert isinstance(base, dict)
    world = base["world"]
    assert isinstance(world, dict)
    parameters = dict(world["parameters"])
    parameters.update(overrides)
    config = _variant(parameters)
    mechanism = SupplyChainMechanism()
    mechanism.validate_config(config.world)
    from agent_tools.fixtures import fixture_state
    from components.protocols.sequential import SequentialProtocol

    protocol = SequentialProtocol(dict(config.protocol_parameters))
    state = fixture_state(config, protocol)
    produce = dict(PRODUCE)
    if "finished_goods_holding_unit_cost" in overrides:
        produce = {"produce": 90}
    state = step_day(mechanism, config, state, ORDER, SUPPLY, SUPPLY, ALLOCATE, produce)
    maker = state.private["manufacturer"].facts
    return {
        "manufacturer": maker["cumulative_revenue"] - maker["cumulative_cost"],
        "supplier_a": state.private["supplier_a"].facts["cumulative_revenue"]
        - state.private["supplier_a"].facts["cumulative_cost"],
        "supplier_b": state.private["supplier_b"].facts["cumulative_revenue"]
        - state.private["supplier_b"].facts["cumulative_cost"],
        "logistics": state.private["logistics"].facts["cumulative_revenue"]
        - state.private["logistics"].facts["cumulative_cost"],
    }


def test_draft_preserves_supplied_inputs_and_behaviors() -> None:
    manifest = JobManifest(request=experiment_request(), simulation=draft_simulation())
    assert len(manifest.request.supplied_inputs) == 19
    assert len(manifest.request.actor_behaviors) == 4
    params = SupplyChainParameters.from_json_values(manifest.simulation.world.parameters)
    assert params.horizon_days == 9
    assert manifest.simulation.max_steps == 36


def test_initial_conditions_are_enforced() -> None:
    mechanism, _, _ = mechanism_and_state()
    base = draft_data()["simulation"]
    assert isinstance(base, dict)
    world = base["world"]
    assert isinstance(world, dict)
    parameters = dict(world["parameters"])
    parameters["initial_manufacturer_components"] = {"A": 100, "B": 150}
    variant = _variant(parameters)
    from agent_tools.fixtures import fixture_state
    from components.protocols.sequential import SequentialProtocol

    protocol = SequentialProtocol(dict(variant.protocol_parameters))
    state = fixture_state(variant, protocol)
    with pytest.raises(ValueError, match="Initial manufacturer facts"):
        mechanism.validate_state(variant.world, state)
    parameters["initial_manufacturer_components"] = {"A": 150, "B": 150}
    parameters["supplier_daily_capacity"] = {"supplier_a": 70, "supplier_b": 100}
    variant = _variant(parameters)
    state = fixture_state(variant, protocol)
    with pytest.raises(ValueError, match="Initial facts for supplier_a"):
        mechanism.validate_state(variant.world, state)
    parameters["supplier_daily_capacity"] = {"supplier_a": 100, "supplier_b": 100}
    parameters["finished_selling_price"] = 110.0
    variant = _variant(parameters)
    state = fixture_state(variant, protocol)
    with pytest.raises(ValueError, match="Initial manufacturer terms"):
        mechanism.validate_state(variant.world, state)
    parameters["finished_selling_price"] = 100.0
    parameters["component_prices"] = {"A": 25.0, "B": 20.0}
    variant = _variant(parameters)
    state = fixture_state(variant, protocol)
    with pytest.raises(ValueError, match="Initial manufacturer terms"):
        mechanism.validate_state(variant.world, state)


def test_capacity_and_demand_changes_alter_behavior() -> None:
    profits = _day_one_profits({"finished_selling_price": 110.0})
    assert profits["manufacturer"] == 2660.0 + 800.0
    profits = _day_one_profits({"component_prices": {"A": 25.0, "B": 20.0}})
    assert profits["manufacturer"] == 2660.0 - 400.0
    assert profits["supplier_a"] == 540.0 + 400.0
    profits = _day_one_profits(
        {"supplier_unit_production_cost": {"supplier_a": 13.0, "supplier_b": 12.0}}
    )
    assert profits["supplier_a"] == 540.0 - 80.0
    profits = _day_one_profits({"assembly_unit_cost": 16.0})
    assert profits["manufacturer"] == 2660.0 - 80.0
    profits = _day_one_profits({"transport_unit_charge": 6.0})
    assert profits["manufacturer"] == 2660.0 - 160.0
    assert profits["logistics"] == 320.0 + 160.0
    profits = _day_one_profits({"transport_unit_operating_cost": 4.0})
    assert profits["logistics"] == 320.0 - 160.0
    profits = _day_one_profits({"manufacturer_component_holding_unit_cost": 2.0})
    assert profits["manufacturer"] == 2660.0 - 140.0
    profits = _day_one_profits({"supplier_holding_unit_cost": 1.5})
    assert profits["supplier_a"] == 540.0 - 200.0
    assert profits["supplier_b"] == 540.0 - 200.0


def test_finished_goods_holding_uses_closing_finished_stock() -> None:
    mechanism, config, state = mechanism_and_state()
    first = step_day(mechanism, config, state, ORDER, SUPPLY, SUPPLY, ALLOCATE, {"produce": 90})
    maker = first.private["manufacturer"].facts
    assert maker["finished"] == 10
    # Procurement 3200 + assembly 1350 + freight 800 + comp holding 120 + finished 20.
    assert maker["cumulative_cost"] == 3200.0 + 1350.0 + 800.0 + 120.0 + 20.0
    profits = _day_one_profits({"finished_goods_holding_unit_cost": 3.0})
    # Revenue 80*100=8000 (10 units remain in finished stock); costs 3200+1350+800+120+30.
    assert profits["manufacturer"] == 8000.0 - (3200.0 + 1350.0 + 800.0 + 120.0 + 30.0)


def test_capacity_limits_and_schedule_are_enforced() -> None:
    from agent_tools.fixtures import fixture_state
    from components.protocols.sequential import SequentialProtocol
    from simulation_core.types import Action, WorldState

    data = draft_data()["simulation"]
    assert isinstance(data, dict)
    data = dict(data)
    world = dict(data["world"])
    parameters = dict(world["parameters"])
    parameters["supplier_daily_capacity"] = {"supplier_a": 70, "supplier_b": 100}
    world["parameters"] = parameters
    private = dict(world["initial_private_state"])
    supplier = dict(private["supplier_a"])
    supplier["facts"] = {**supplier["facts"], "capacity": 70}
    private["supplier_a"] = supplier
    world["initial_private_state"] = private
    data["world"] = world
    data["assumptions"] = []
    variant = SimulationConfig.from_json_values(data)
    mechanism = SupplyChainMechanism()
    mechanism.validate_config(variant.world)
    protocol = SequentialProtocol(dict(variant.protocol_parameters))
    state = fixture_state(variant, protocol)
    mechanism.validate_state(variant.world, state)
    order_result = mechanism.transition(
        variant.world,
        state,
        (Action(actor_id="manufacturer", kind="order", payload=dict(ORDER)),),
    )
    supply_state = WorldState(
        tick=1,
        phase="d1_supply",
        public=order_result.public,
        private=dict(order_result.private_updates),
    )
    with pytest.raises(ValueError, match="above capacity"):
        mechanism.validate_actions(
            variant.world,
            supply_state,
            (
                Action(
                    actor_id="supplier_a",
                    kind="supply",
                    payload={"produce": 80, "fulfill": 0, "ship_request": 0, "priority": 0},
                ),
                Action(
                    actor_id="supplier_b",
                    kind="supply",
                    payload={"produce": 0, "fulfill": 0, "ship_request": 0, "priority": 0},
                ),
            ),
        )
    mechanism.validate_actions(
        variant.world,
        supply_state,
        (
            Action(
                actor_id="supplier_a",
                kind="supply",
                payload={"produce": 70, "fulfill": 0, "ship_request": 0, "priority": 0},
            ),
            Action(
                actor_id="supplier_b",
                kind="supply",
                payload={"produce": 0, "fulfill": 0, "ship_request": 0, "priority": 0},
            ),
        ),
    )


def test_horizon_and_schedule_mismatch_rejected() -> None:
    parameters = dict(draft_simulation().world.parameters)
    parameters["horizon_days"] = 2
    with pytest.raises(ValueError, match="span days 1 through the horizon"):
        SupplyChainParameters.from_json_values(parameters)
    parameters = dict(draft_simulation().world.parameters)
    parameters["capacity_schedule"] = [
        {"start_day": 1, "end_day": 2, "capacity": 200},
        {"start_day": 4, "end_day": 9, "capacity": 200},
    ]
    with pytest.raises(ValueError, match="contiguous"):
        SupplyChainParameters.from_json_values(parameters)
    mechanism = SupplyChainMechanism()
    assert mechanism.required_action_schemas(draft_simulation().world)["manufacturer"]


def test_transit_days_and_conventions_reject_alternatives() -> None:
    base = dict(draft_simulation().world.parameters)
    for field, bad in (
        ("transit_days", 2),
        ("quantity_unit", "continuous"),
        ("order_policy", "reset_daily"),
        ("unmet_demand_policy", "backlog"),
        ("holding_cost_basis", "average_stock"),
        ("transfer_recognition", "at_sale"),
        ("opening_stock_cost", "revalued"),
        ("priority_effect", "binding"),
    ):
        parameters = dict(base)
        parameters[field] = bad
        with pytest.raises(ValueError, match="Input should be"):
            SupplyChainParameters.from_json_values(parameters)


def test_mechanism_requires_exact_roles() -> None:
    data = draft_data()["simulation"]
    assert isinstance(data, dict)
    data = dict(data)
    world = dict(data["world"])
    actors = list(world["actors"])
    mechanism = SupplyChainMechanism()
    world["actors"] = actors[:-1]
    private = dict(world["initial_private_state"])
    private.pop("logistics")
    world["initial_private_state"] = private
    permissions = dict(data["permissions"])
    permissions.pop("logistics")
    data["world"] = world
    data["permissions"] = permissions
    data["assumptions"] = []
    reduced = SimulationConfig.from_json_values(data)
    with pytest.raises(ValueError, match="exactly the four chain roles"):
        mechanism.validate_config(reduced.world)


def test_max_steps_bounds_the_run() -> None:
    from helpers import experiment_registry

    simulation = offline_simulation("baseline")
    data = simulation.model_dump(mode="json")
    data["max_steps"] = 4
    data["assumptions"] = []
    short = SimulationConfig.from_json_values(data)
    registry = experiment_registry()
    request = experiment_request().model_copy(
        update={
            "supplied_inputs": tuple(
                item
                for item in experiment_request().supplied_inputs
                if item.name != "phase transition budget"
            )
        }
    )
    artifact = JobRunner(LocalBackend(registry)).run(request, short)
    assert artifact.result.status == "step_limit"
    assert len(artifact.result.outcomes) == 4
    full = run_offline("baseline")
    assert full.result.status == "completed"
    assert len(full.result.outcomes) == 36
    assert full.result.final_state.tick == 36
    assert SupplyChainParameters.from_json_values(short.world.parameters).horizon_days == 9
