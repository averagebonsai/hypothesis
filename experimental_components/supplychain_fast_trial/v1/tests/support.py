"""Shared offline fixtures: scripted/sequenced policies and config builders."""

import json
from collections.abc import Sequence

from experiment_extension.supplychain import (
    LOGISTICS,
    MANUFACTURER,
    SUPPLIER_A,
    SUPPLIER_B,
    LogisticsAllocation,
    MakeAction,
    OrderAction,
    SupplierOffer,
    SupplyChainMechanism,
    schedule_phases,
)

from components.library import standard_registry
from simulation_core.execution import JobResult, JobRunner, LocalBackend
from simulation_core.policy import Policy
from simulation_core.registry import ComponentRegistry
from simulation_core.request import ExperimentRequest
from simulation_core.types import Action, Decision, Observation, SimulationConfig

PARAMS: dict = {
    "horizon_days": 9,
    "capacity_schedule": [
        {"start_day": 1, "end_day": 2, "capacity": 200},
        {"start_day": 3, "end_day": 6, "capacity": 80},
        {"start_day": 7, "end_day": 9, "capacity": 200},
    ],
    "initial_manufacturer_components": {"A": 150, "B": 150},
    "initial_supplier_inventory": {"supplier_a": 200, "supplier_b": 200},
    "supplier_daily_capacity": {"supplier_a": 100, "supplier_b": 100},
    "manufacturer_daily_capacity": 100,
    "daily_demand": 80,
    "initial_finished_goods": 0,
    "transit_days": 1,
    "finished_selling_price": 100.0,
    "component_prices": {"A": 20.0, "B": 20.0},
    "supplier_unit_production_cost": {"supplier_a": 12.0, "supplier_b": 12.0},
    "assembly_unit_cost": 15.0,
    "transport_unit_charge": 5.0,
    "transport_unit_operating_cost": 3.0,
    "manufacturer_component_holding_unit_cost": 1.0,
    "supplier_holding_unit_cost": 0.5,
    "finished_goods_holding_unit_cost": 2.0,
}

MANUFACTURER_FACTS: dict = {
    "comp_a": 150,
    "comp_b": 150,
    "finished_goods": 0,
    "backlog_a": 0,
    "backlog_b": 0,
    "demand_today": 80,
    "cum_sold": 0,
    "cum_lost": 0,
    "cum_revenue": 0.0,
    "cum_procurement": 0.0,
    "cum_logistics": 0.0,
    "cum_assembly": 0.0,
    "cum_holding": 0.0,
    "last_order_a": 0,
    "last_order_b": 0,
    "last_arrivals_a": 0,
    "last_arrivals_b": 0,
    "last_commit_a": 0,
    "last_commit_b": 0,
    "last_dispatch_a": 0,
    "last_dispatch_b": 0,
    "last_produced": 0,
    "last_sold": 0,
    "last_lost": 0,
    "day": 1,
}

SUPPLIER_FACTS: dict = {
    "inventory": 200,
    "backlog": 0,
    "cum_produced": 0,
    "cum_offered": 0,
    "cum_dispatched": 0,
    "cum_revenue": 0.0,
    "cum_production_cost": 0.0,
    "cum_holding": 0.0,
    "last_order": 0,
    "last_produce": 0,
    "last_offer": 0,
    "last_dispatch": 0,
    "day": 1,
}

LOGISTICS_FACTS: dict = {
    "request_a": 0,
    "request_b": 0,
    "cum_dispatched": 0,
    "cum_revenue": 0.0,
    "cum_operating": 0.0,
    "cum_unused": 0,
    "last_alloc_a": 0,
    "last_alloc_b": 0,
    "day": 1,
}

INITIAL_PUBLIC: dict = {
    "day": 1,
    "capacity": 200,
    "disrupted": False,
    "arrivals_today": {"A": 0, "B": 0},
    "last_dispatch": {"A": 0, "B": 0},
    "pending_offers": {"supplier_a": 0, "supplier_b": 0},
    "backlogs": {"supplier_a": 0, "supplier_b": 0},
    "in_transit": [],
    "history": [],
    "totals": {
        "sold": 0,
        "lost": 0,
        "produced_fg": 0,
        "dispatched": 0,
        "consumer_revenue": 0.0,
        "supplier_production_cost": 0.0,
        "assembly_cost": 0.0,
        "transport_operating_cost": 0.0,
        "holding_cost": 0.0,
        "consolidated": 0.0,
    },
    "today": {
        "order_a": 0,
        "order_b": 0,
        "produce_a": 0,
        "produce_b": 0,
        "offer_a": 0,
        "offer_b": 0,
        "alloc_a": 0,
        "alloc_b": 0,
    },
}

PERMISSIONS: dict = {
    "manufacturer": {
        "public_fields": [
            "day",
            "capacity",
            "disrupted",
            "arrivals_today",
            "last_dispatch",
            "pending_offers",
        ],
        "private_fields": list(MANUFACTURER_FACTS),
        "readable_memory": False,
        "writable_private_fields": [],
        "writable_memory": False,
    },
    "supplier_a": {
        "public_fields": ["day", "capacity", "disrupted"],
        "private_fields": list(SUPPLIER_FACTS),
        "readable_memory": False,
        "writable_private_fields": [],
        "writable_memory": False,
    },
    "supplier_b": {
        "public_fields": ["day", "capacity", "disrupted"],
        "private_fields": list(SUPPLIER_FACTS),
        "readable_memory": False,
        "writable_private_fields": [],
        "writable_memory": False,
    },
    "logistics": {
        "public_fields": ["day", "capacity", "disrupted"],
        "private_fields": list(LOGISTICS_FACTS),
        "readable_memory": False,
        "writable_private_fields": [],
        "writable_memory": False,
    },
}


class SequencePolicy(Policy):
    """Deterministic offline stand-in: replays a queued action per call."""

    def __init__(self, actions: Sequence[tuple[str, dict]]) -> None:
        self._actions = list(actions)

    def required_observation_fields(self) -> frozenset[str]:
        return frozenset()

    def choose_action(self, observation: Observation) -> Decision:
        kind, payload = self._actions.pop(0)
        return Decision(
            action=Action(actor_id=observation.actor_id, kind=kind, payload=dict(payload)),
            rationale="Sequenced offline stand-in for a fixed action script.",
        )


def make_registry() -> ComponentRegistry:
    registry = standard_registry()
    registry.mechanisms["test.supplychain.v1"] = SupplyChainMechanism
    registry.action_schemas["test.order.v1"] = OrderAction
    registry.action_schemas["test.offer.v1"] = SupplierOffer
    registry.action_schemas["test.allocate.v1"] = LogisticsAllocation
    registry.action_schemas["test.make.v1"] = MakeAction
    return registry


def actor_entry(
    actor_id: str, kinds: dict[str, str], policy_id: str, policy_parameters: dict
) -> dict:
    return {
        "id": actor_id,
        "kind": "organization",
        "attributes": {},
        "action_space": {"schemas": kinds},
        "policy_id": policy_id,
        "policy_parameters": policy_parameters,
    }


ASSUMPTIONS: list = [
    {
        "path": "/max_steps",
        "value": 36,
        "source": "model",
        "rationale": "Nine days times four decision phases per day.",
    },
    {
        "path": "/world/parameters/transit_days",
        "value": 1,
        "source": "user",
        "rationale": "Dispatched components arrive at the start of the next day.",
    },
]


def base_config(policy_map: dict[str, tuple[str, dict]]) -> SimulationConfig:
    """Full 36-phase config with a chosen policy per actor."""
    entries = {
        MANUFACTURER: {"order": "test.order.v1", "produce": "test.make.v1"},
        SUPPLIER_A: {"offer": "test.offer.v1"},
        SUPPLIER_B: {"offer": "test.offer.v1"},
        LOGISTICS: {"allocate": "test.allocate.v1"},
    }
    actors = [
        actor_entry(aid, kinds, policy_map[aid][0], policy_map[aid][1])
        for aid, kinds in entries.items()
    ]
    return SimulationConfig.from_json_values(
        json.loads(
            json.dumps(
                {
                    "world": {
                        "actors": actors,
                        "parameters": PARAMS,
                        "initial_public_state": INITIAL_PUBLIC,
                        "initial_private_state": {
                            "manufacturer": {"facts": MANUFACTURER_FACTS, "memory": {}},
                            "supplier_a": {"facts": SUPPLIER_FACTS, "memory": {}},
                            "supplier_b": {"facts": SUPPLIER_FACTS, "memory": {}},
                            "logistics": {"facts": LOGISTICS_FACTS, "memory": {}},
                        },
                    },
                    "mechanism_id": "test.supplychain.v1",
                    "protocol_id": "sequential.v1",
                    "protocol_parameters": {"phases": schedule_phases(9)},
                    "permissions": PERMISSIONS,
                    "max_steps": 36,
                    "assumptions": ASSUMPTIONS,
                }
            )
        )
    )


def scripted_config() -> SimulationConfig:
    """Full 36-phase config with zero-action scripted policies."""
    return base_config(
        {
            MANUFACTURER: (
                "scripted.v1",
                {"kind": "order", "payload": {"order_a": 0, "order_b": 0, "priority": "none"}},
            ),
            SUPPLIER_A: (
                "scripted.v1",
                {"kind": "offer", "payload": {"produce": 0, "offer": 0, "priority_request": False}},
            ),
            SUPPLIER_B: (
                "scripted.v1",
                {"kind": "offer", "payload": {"produce": 0, "offer": 0, "priority_request": False}},
            ),
            LOGISTICS: (
                "scripted.v1",
                {"kind": "allocate", "payload": {"alloc_a": 0, "alloc_b": 0}},
            ),
        }
    )


def run_with_sequences(script: dict[str, list[tuple[str, dict]]]) -> JobResult:
    """Run the full horizon with per-actor sequenced offline policies."""
    config = base_config({aid: (f"seq.{aid}", {}) for aid in script})
    registry = make_registry()
    for actor_id, actions in script.items():
        policy = SequencePolicy(list(actions))
        registry.policies[f"seq.{actor_id}"] = lambda _params, _p=policy: _p
    runner = JobRunner(LocalBackend(registry))
    return runner.run(ExperimentRequest(hypothesis="offline sequenced run"), config)
