"""Shared offline fixtures: draft loading, inline request, deterministic test policy."""

import json
from pathlib import Path

from experiment_extension.mechanism import SupplyChainMechanism
from experiment_extension.schemas import (
    AllocateAction,
    OrderAction,
    ProduceAction,
    SupplyAction,
)
from pydantic import JsonValue

from agent_tools.fixtures import fixture_state
from components.library import standard_registry
from components.protocols.sequential import SequentialProtocol
from simulation_core.execution import JobManifest, JobResult, JobRunner, LocalBackend
from simulation_core.policy import Policy
from simulation_core.registry import ComponentRegistry
from simulation_core.request import ExperimentRequest
from simulation_core.types import (
    Action,
    Decision,
    Observation,
    SimulationConfig,
    WorldState,
)

HYPOTHESIS = (
    "How do decentralized LLM-driven supply-chain participants respond to a flood, and "
    "what production, service, cost and recovery bottlenecks emerge over nine days?"
)

SUPPLIED_INPUTS: list[dict[str, JsonValue]] = [
    {"name": "horizon_days", "value": 9, "target_path": "/world/parameters/horizon_days"},
    {
        "name": "capacity_schedule",
        "value": [
            {"start_day": 1, "end_day": 2, "capacity": 200},
            {"start_day": 3, "end_day": 6, "capacity": 80},
            {"start_day": 7, "end_day": 9, "capacity": 200},
        ],
        "target_path": "/world/parameters/capacity_schedule",
    },
    {
        "name": "initial_manufacturer_components",
        "value": {"A": 150, "B": 150},
        "target_path": "/world/parameters/initial_manufacturer_components",
    },
    {
        "name": "initial_supplier_inventory",
        "value": {"supplier_a": 200, "supplier_b": 200},
        "target_path": "/world/parameters/initial_supplier_inventory",
    },
    {
        "name": "supplier_daily_capacity",
        "value": {"supplier_a": 100, "supplier_b": 100},
        "target_path": "/world/parameters/supplier_daily_capacity",
    },
    {
        "name": "manufacturer_daily_capacity",
        "value": 100,
        "target_path": "/world/parameters/manufacturer_daily_capacity",
    },
    {"name": "daily_demand", "value": 80, "target_path": "/world/parameters/daily_demand"},
    {
        "name": "initial_finished_goods",
        "value": 0,
        "target_path": "/world/parameters/initial_finished_goods",
    },
    {"name": "transit_days", "value": 1, "target_path": "/world/parameters/transit_days"},
    {
        "name": "finished_selling_price",
        "value": 100.0,
        "target_path": "/world/parameters/finished_selling_price",
    },
    {
        "name": "component_prices",
        "value": {"A": 20.0, "B": 20.0},
        "target_path": "/world/parameters/component_prices",
    },
    {
        "name": "supplier_unit_production_cost",
        "value": {"supplier_a": 12.0, "supplier_b": 12.0},
        "target_path": "/world/parameters/supplier_unit_production_cost",
    },
    {
        "name": "assembly_unit_cost",
        "value": 15.0,
        "target_path": "/world/parameters/assembly_unit_cost",
    },
    {
        "name": "transport_unit_charge",
        "value": 5.0,
        "target_path": "/world/parameters/transport_unit_charge",
    },
    {
        "name": "transport_unit_operating_cost",
        "value": 3.0,
        "target_path": "/world/parameters/transport_unit_operating_cost",
    },
    {
        "name": "manufacturer_component_holding_unit_cost",
        "value": 1.0,
        "target_path": "/world/parameters/manufacturer_component_holding_unit_cost",
    },
    {
        "name": "supplier_holding_unit_cost",
        "value": 0.5,
        "target_path": "/world/parameters/supplier_holding_unit_cost",
    },
    {
        "name": "finished_goods_holding_unit_cost",
        "value": 2.0,
        "target_path": "/world/parameters/finished_goods_holding_unit_cost",
    },
    {"name": "phase transition budget", "value": 36, "target_path": "/max_steps"},
]

ACTOR_BEHAVIORS: list[dict[str, JsonValue]] = [
    {
        "actor_id": "manufacturer",
        "objective": "Maximize fulfilled customer demand while minimizing inventory holding and procurement costs and production disruptions.",
        "behavioral_instructions": "Use only your own inventory, demand, orders, capacity and accounting, plus explicitly communicated commitments and shipment confirmations. Request orders/priorities in the ordering phase and production in the later manufacturing phase; no premature use of in-transit components.",
        "background": "",
    },
    {
        "actor_id": "supplier_a",
        "objective": "Maximize revenue earned on actual dispatched Component A while minimizing production, holding and unfulfilled-order costs.",
        "behavioral_instructions": "Control only Component A. Use your own inventory/capacity/costs/backlog and received orders. Do not observe Supplier B's inventory, production decisions or order backlog. Priorities are requests, not guaranteed allocations.",
        "background": "",
    },
    {
        "actor_id": "supplier_b",
        "objective": "Maximize revenue earned on actual dispatched Component B while minimizing production, holding and unfulfilled-order costs.",
        "behavioral_instructions": "Control only Component B. Use your own inventory/capacity/costs/backlog and received orders. Do not observe Supplier A's inventory, production decisions or order backlog. Priorities are requests, not guaranteed allocations.",
        "background": "",
    },
    {
        "actor_id": "logistics",
        "objective": "Maximize completed deliveries and transport revenue while minimizing unused capacity, operating costs and unfulfilled shipment requests.",
        "behavioral_instructions": "Use submitted shipment requests/priorities, current transport capacity, your pending shipments and own costs. Do not observe the manufacturer's inventory or demand, or suppliers' true inventories/production/costs. Allocate no more than offers and aggregate capacity.",
        "background": "",
    },
]


def candidate_paths() -> list[Path]:
    """Ordered candidate locations for the simulation configuration.

    The deployed worker exposes ``/job/manifest.json``; the versioned bundle
    ships ``job.example.json`` (a JobManifest); ``draft.json`` is a CodingPlan
    fallback for the authoring container only. Every candidate carries the
    simulation under the ``simulation`` key. Nothing here depends on CWD alone.
    """
    root = Path(__file__).resolve().parent.parent
    return [
        Path("/job/manifest.json"),
        Path.cwd() / "job.example.json",
        Path.cwd() / "draft.json",
        root / "job.example.json",
        root / "draft.json",
    ]


def candidate_data() -> dict[str, JsonValue]:
    for path in candidate_paths():
        if path.is_file():
            data = json.loads(path.read_text())
            assert isinstance(data, dict), f"{path} must hold a JSON object"
            assert isinstance(data.get("simulation"), dict), (
                f"{path} must carry the simulation under 'simulation'"
            )
            return data
    searched = ", ".join(str(path) for path in candidate_paths())
    raise FileNotFoundError(f"No candidate file found; searched: {searched}")


def draft_data() -> dict[str, JsonValue]:
    """Load the candidate (manifest or authoring-plan) JSON object."""
    return candidate_data()


def draft_simulation() -> SimulationConfig:
    return SimulationConfig.from_json_values(draft_data()["simulation"])


def experiment_request() -> ExperimentRequest:
    return ExperimentRequest.from_json_values(
        {
            "hypothesis": HYPOTHESIS,
            "execution_kind": "agent_simulation",
            "supplied_inputs": SUPPLIED_INPUTS,
            "actor_behaviors": ACTOR_BEHAVIORS,
        }
    )


def draft_manifest() -> JobManifest:
    return JobManifest(request=experiment_request(), simulation=draft_simulation())


class TestPlanPolicy(Policy):
    """Deterministic offline stand-in with scenario-coded legal actions."""

    def __init__(self, parameters: dict[str, JsonValue]) -> None:
        scenario = parameters.get("scenario", "baseline")
        if scenario not in {"baseline", "hoard"}:
            raise ValueError("Unknown offline test scenario")
        self.scenario = scenario

    def required_observation_fields(self) -> frozenset[str]:
        return frozenset()

    def choose_action(self, observation: Observation) -> Decision:
        stage = observation.phase.rsplit("_", 1)[-1]
        actor_id = observation.actor_id
        visible = observation.visible
        facts = observation.private.facts
        day = visible["day"]
        assert isinstance(day, int)
        if actor_id == "manufacturer" and stage == "order":
            action = Action(
                actor_id=actor_id,
                kind="order",
                payload={"order_a": 80, "order_b": 80, "priority_a": 0, "priority_b": 0},
            )
        elif actor_id == "manufacturer" and stage == "settle":
            comp_a = facts["comp_a"]
            comp_b = facts["comp_b"]
            capacity = facts["capacity"]
            assert isinstance(comp_a, int) and isinstance(comp_b, int) and isinstance(capacity, int)
            target = 0 if (self.scenario == "hoard" and day <= 6) else 80
            action = Action(
                actor_id=actor_id,
                kind="produce",
                payload={"produce": min(target, comp_a, comp_b, capacity)},
            )
        elif actor_id in {"supplier_a", "supplier_b"} and stage == "supply":
            capacity = facts["capacity"]
            backlog = facts["backlog"]
            inventory = facts["inventory"]
            assert (
                isinstance(capacity, int)
                and isinstance(backlog, int)
                and isinstance(inventory, int)
            )
            produce = min(80, capacity)
            action = Action(
                actor_id=actor_id,
                kind="supply",
                payload={
                    "produce": produce,
                    "fulfill": min(80, backlog),
                    "ship_request": min(80, inventory + produce),
                    "priority": 0,
                },
            )
        elif actor_id == "logistics" and stage == "ship":
            offer_a = visible["offer_a"]
            offer_b = visible["offer_b"]
            capacity = visible["capacity"]
            assert (
                isinstance(offer_a, int) and isinstance(offer_b, int) and isinstance(capacity, int)
            )
            allocate_a = min(offer_a, capacity // 2)
            allocate_b = min(offer_b, capacity - allocate_a)
            action = Action(
                actor_id=actor_id,
                kind="allocate",
                payload={"allocate_a": allocate_a, "allocate_b": allocate_b},
            )
        else:
            raise ValueError(f"No test action for {actor_id} in {observation.phase}")
        return Decision(
            action=action,
            rationale="Deterministic offline test plan: emit the scenario-coded legal action.",
            memory_update=None,
            private_updates={},
        )


def experiment_registry() -> ComponentRegistry:
    registry = standard_registry()
    simulation = draft_data()["simulation"]
    assert isinstance(simulation, dict)
    mechanism_id = simulation["mechanism_id"]
    assert isinstance(mechanism_id, str)
    registry.mechanisms[mechanism_id] = SupplyChainMechanism
    world = simulation["world"]
    assert isinstance(world, dict)
    actors = world["actors"]
    assert isinstance(actors, list)
    for actor in actors:
        assert isinstance(actor, dict)
        action_space = actor["action_space"]
        assert isinstance(action_space, dict)
        schemas = action_space["schemas"]
        assert isinstance(schemas, dict)
        for schema_id in schemas.values():
            assert isinstance(schema_id, str)
            if "orderaction" in schema_id:
                registry.action_schemas[schema_id] = OrderAction
            elif "produceaction" in schema_id:
                registry.action_schemas[schema_id] = ProduceAction
            elif "supplyaction" in schema_id:
                registry.action_schemas[schema_id] = SupplyAction
            elif "allocateaction" in schema_id:
                registry.action_schemas[schema_id] = AllocateAction
            else:
                raise ValueError(f"Unknown test schema: {schema_id}")
    registry.policies["test.plan.v1"] = TestPlanPolicy
    return registry


def offline_simulation(scenario: str = "baseline") -> SimulationConfig:
    data = draft_data()["simulation"]
    assert isinstance(data, dict)
    world = data["world"]
    assert isinstance(world, dict)
    actors = world["actors"]
    assert isinstance(actors, list)
    for actor in actors:
        assert isinstance(actor, dict)
        params = actor["policy_parameters"]
        assert isinstance(params, dict)
        actor["policy_id"] = "test.plan.v1"
        actor["policy_parameters"] = {"scenario": scenario, "behavior": params["behavior"]}
    return SimulationConfig.from_json_values(data)


def run_offline(scenario: str = "baseline") -> JobResult:
    simulation = offline_simulation(scenario)
    registry = experiment_registry()
    return JobRunner(LocalBackend(registry)).run(experiment_request(), simulation)


def mechanism_and_state() -> tuple[SupplyChainMechanism, SimulationConfig, WorldState]:
    config = draft_simulation()
    protocol = SequentialProtocol(dict(config.protocol_parameters))
    return SupplyChainMechanism(), config, fixture_state(config, protocol)


def step_day(
    mechanism: SupplyChainMechanism,
    config: SimulationConfig,
    state: WorldState,
    order: dict[str, JsonValue],
    supply_a: dict[str, JsonValue],
    supply_b: dict[str, JsonValue],
    allocate: dict[str, JsonValue],
    produce: dict[str, JsonValue],
) -> WorldState:
    """Drive four mechanism transitions for one day, advancing tick and phase."""
    protocol = SequentialProtocol(dict(config.protocol_parameters))
    world = config.world
    batches = (
        (Action(actor_id="manufacturer", kind="order", payload=order),),
        (
            Action(actor_id="supplier_a", kind="supply", payload=supply_a),
            Action(actor_id="supplier_b", kind="supply", payload=supply_b),
        ),
        (Action(actor_id="logistics", kind="allocate", payload=allocate),),
        (Action(actor_id="manufacturer", kind="produce", payload=produce),),
    )
    for batch in batches:
        mechanism.validate_actions(world, state, batch)
        result = mechanism.transition(world, state, batch)
        state = WorldState(
            tick=state.tick + 1,
            phase=protocol.next_phase(world, state),
            public=result.public,
            private=dict(result.private_updates),
        )
        mechanism.validate_state(world, state)
    return state


def settle_metrics(artifact: JobResult, day: int) -> dict[str, JsonValue]:
    for event in artifact.result.events:
        if (
            event.actions
            and event.actions[0].kind == "produce"
            and event.outcome is not None
            and event.outcome.metrics.get("day") == day
        ):
            return dict(event.outcome.metrics)
    raise AssertionError(f"No settle outcome for day {day}")
