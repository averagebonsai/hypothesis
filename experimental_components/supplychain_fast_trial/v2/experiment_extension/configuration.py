"""Single source of truth for the candidate configuration.

Tests and the draft generator both build from these constants, so the sealed
bundle (which ships only experiment_extension/ and tests/) never needs to
read draft.json or /inputs/task.json at runtime. Values mirror the user
request's supplied inputs and actor behaviors verbatim.
"""

from typing import Any

from .supplychain import LOGISTICS, MANUFACTURER, SUPPLIER_A, SUPPLIER_B, schedule_phases

LLM_MODEL = "muse-spark-1.3-contributor"

WORLD_PARAMETERS: dict[str, Any] = {
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

MANUFACTURER_FACTS: dict[str, Any] = {
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

SUPPLIER_FACTS: dict[str, Any] = {
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

LOGISTICS_FACTS: dict[str, Any] = {
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

INITIAL_PUBLIC_STATE: dict[str, Any] = {
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

PERMISSIONS: dict[str, Any] = {
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

ASSUMPTIONS: list[dict[str, Any]] = [
    {
        "path": "/world/parameters/capacity_schedule",
        "value": [
            {"start_day": 1, "end_day": 2, "capacity": 200},
            {"start_day": 3, "end_day": 6, "capacity": 80},
            {"start_day": 7, "end_day": 9, "capacity": 200},
        ],
        "source": "user",
        "rationale": (
            "The flood cuts shared transport to 80 units/day on days 3-6 with restoration on day 7; "
            "actors observe only current capacity and disruption status as changes occur, never the "
            "advance schedule."
        ),
    },
    {
        "path": "/world/parameters/transit_days",
        "value": 1,
        "source": "user",
        "rationale": "Dispatched components arrive at the start of the next day.",
    },
    {
        "path": "/max_steps",
        "value": 36,
        "source": "model",
        "rationale": (
            "Nine days times four decision phases (order, joint supply, ship, make); the finite horizon "
            "is known but flood and recovery dates are not announced."
        ),
    },
    {
        "path": "/world/parameters/daily_demand",
        "value": 80,
        "source": "user",
        "rationale": (
            "Unmet demand is lost sales, never backlog; no numeric shortage penalty is imposed, so "
            "service is tracked as lost-sales KPIs."
        ),
    },
    {
        "path": "/world/parameters/transport_unit_charge",
        "value": 5.0,
        "source": "model",
        "rationale": (
            "Procurement and logistics charges are recognized at dispatch and assembly at production; "
            "opening stocks are sunk with no revaluation or salvage."
        ),
    },
    {
        "path": "/world/parameters/manufacturer_component_holding_unit_cost",
        "value": 1.0,
        "source": "model",
        "rationale": (
            "Holding costs apply to closing on-hand stock only, never in-transit stock; no cash or "
            "borrowing constraint is imposed."
        ),
    },
    {
        "path": "/world/parameters/initial_manufacturer_components",
        "value": {"A": 150, "B": 150},
        "source": "user",
        "rationale": "Opening component stocks are hypothetical experimental assumptions.",
    },
    {
        "path": "/world/parameters/supplier_daily_capacity",
        "value": {"supplier_a": 100, "supplier_b": 100},
        "source": "user",
        "rationale": "Each supplier can produce at most 100 units per day.",
    },
]

INSTRUCTIONS: dict[str, str] = {
    "manufacturer": (
        "You are the manufacturer. Each day has four phases in order: manufacturer order "
        "(action kind order), joint supplier offers, logistics allocation, then manufacturer "
        "production (action kind produce). Act only in your phases with the phase-appropriate "
        "kind. Quantities are integer units. One finished product needs one unit of each "
        "component. You observe current transport capacity and disruption status each day; "
        "the future capacity schedule is not announced. Your history is recorded by the "
        "mechanism: leave memory_update null and private_updates empty."
    ),
    "supplier_a": (
        "You control Component A only. Each day, in the joint supply phase, submit one "
        "offer action with integer production and offer quantities. Offers cannot exceed "
        "your outstanding backlog or physically available stock. You observe current "
        "transport capacity and the orders sent to you; Supplier B's inventory, production "
        "and backlog are never visible. Priority requests do not guarantee allocation. "
        "Your history is recorded by the mechanism: leave memory_update null and "
        "private_updates empty."
    ),
    "supplier_b": (
        "You control Component B only. Each day, in the joint supply phase, submit one "
        "offer action with integer production and offer quantities. Offers cannot exceed "
        "your outstanding backlog or physically available stock. You observe current "
        "transport capacity and the orders sent to you; Supplier A's inventory, production "
        "and backlog are never visible. Priority requests do not guarantee allocation. "
        "Your history is recorded by the mechanism: leave memory_update null and "
        "private_updates empty."
    ),
    "logistics": (
        "You allocate shared daily transport capacity between the two submitted shipment "
        "offers. Submit one allocate action per day with integer quantities that do not "
        "exceed either offer or the day's capacity. You observe current capacity and the "
        "submitted requests only; you cannot see the manufacturer's inventory or demand, "
        "or suppliers' true stocks and costs. Your history is recorded by the mechanism: "
        "leave memory_update null and private_updates empty."
    ),
}

ACTOR_BEHAVIORS: dict[str, dict[str, str]] = {
    "manufacturer": {
        "actor_id": "manufacturer",
        "objective": (
            "Maximize fulfilled customer demand while minimizing inventory holding and "
            "procurement costs and production disruptions."
        ),
        "behavioral_instructions": (
            "Use only your own inventory, demand, orders, capacity and accounting, plus explicitly "
            "communicated commitments and shipment confirmations. Request orders/priorities in the "
            "ordering phase and production in the later manufacturing phase; no premature use of "
            "in-transit components."
        ),
        "background": "",
    },
    "supplier_a": {
        "actor_id": "supplier_a",
        "objective": (
            "Maximize revenue earned on actual dispatched Component A while minimizing production, "
            "holding and unfulfilled-order costs."
        ),
        "behavioral_instructions": (
            "Control only Component A. Use your own inventory/capacity/costs/backlog and received "
            "orders. Do not observe Supplier B's inventory, production decisions or order backlog. "
            "Priorities are requests, not guaranteed allocations."
        ),
        "background": "",
    },
    "supplier_b": {
        "actor_id": "supplier_b",
        "objective": (
            "Maximize revenue earned on actual dispatched Component B while minimizing production, "
            "holding and unfulfilled-order costs."
        ),
        "behavioral_instructions": (
            "Control only Component B. Use your own inventory/capacity/costs/backlog and received "
            "orders. Do not observe Supplier A's inventory, production decisions or order backlog. "
            "Priorities are requests, not guaranteed allocations."
        ),
        "background": "",
    },
    "logistics": {
        "actor_id": "logistics",
        "objective": (
            "Maximize completed deliveries and transport revenue while minimizing unused capacity, "
            "operating costs and unfulfilled shipment requests."
        ),
        "behavioral_instructions": (
            "Use submitted shipment requests/priorities, current transport capacity, your pending "
            "shipments and own costs. Do not observe the manufacturer's inventory or demand, or "
            "suppliers' true inventories/production/costs. Allocate no more than offers and "
            "aggregate capacity."
        ),
        "background": "",
    },
}

SAFE_FALLBACKS: dict[str, dict[str, dict[str, Any]]] = {
    MANUFACTURER: {
        "order": {"order_a": 0, "order_b": 0, "priority": "none"},
        "produce": {"produce": 0},
    },
    SUPPLIER_A: {"offer": {"produce": 0, "offer": 0, "priority_request": False}},
    SUPPLIER_B: {"offer": {"produce": 0, "offer": 0, "priority_request": False}},
    LOGISTICS: {"allocate": {"alloc_a": 0, "alloc_b": 0}},
}

REQUIRED_FIELDS = ["day", "capacity", "disrupted"]

MAX_STEPS = 36


def component_id(experiment_id: str, kind: str, symbol_name: str) -> str:
    """Mirror agent_tools.workspace.component_id without the toolkit dependency."""
    return f"experimental.{experiment_id}.{kind}.{symbol_name.lower()}.v1"


def schema_ids(experiment_id: str) -> dict[str, str]:
    return {
        "mechanism": component_id(experiment_id, "mechanism", "SupplyChainMechanism"),
        "order": component_id(experiment_id, "action_schema", "OrderAction"),
        "offer": component_id(experiment_id, "action_schema", "SupplierOffer"),
        "allocate": component_id(experiment_id, "action_schema", "LogisticsAllocation"),
        "make": component_id(experiment_id, "action_schema", "MakeAction"),
    }


def llm_actors(experiment_id: str) -> list[dict[str, Any]]:
    ids = schema_ids(experiment_id)
    return [
        {
            "id": "manufacturer",
            "kind": "organization",
            "attributes": {"safe_fallback_actions": SAFE_FALLBACKS["manufacturer"]},
            "action_space": {"schemas": {"order": ids["order"], "produce": ids["make"]}},
            "policy_id": "llm.v1",
            "policy_parameters": {
                "model": LLM_MODEL,
                "instructions": INSTRUCTIONS["manufacturer"],
                "behavior": ACTOR_BEHAVIORS["manufacturer"],
                "required_fields": list(REQUIRED_FIELDS),
            },
        },
        {
            "id": "supplier_a",
            "kind": "organization",
            "attributes": {"safe_fallback_actions": SAFE_FALLBACKS["supplier_a"]},
            "action_space": {"schemas": {"offer": ids["offer"]}},
            "policy_id": "llm.v1",
            "policy_parameters": {
                "model": LLM_MODEL,
                "instructions": INSTRUCTIONS["supplier_a"],
                "behavior": ACTOR_BEHAVIORS["supplier_a"],
                "required_fields": list(REQUIRED_FIELDS),
            },
        },
        {
            "id": "supplier_b",
            "kind": "organization",
            "attributes": {"safe_fallback_actions": SAFE_FALLBACKS["supplier_b"]},
            "action_space": {"schemas": {"offer": ids["offer"]}},
            "policy_id": "llm.v1",
            "policy_parameters": {
                "model": LLM_MODEL,
                "instructions": INSTRUCTIONS["supplier_b"],
                "behavior": ACTOR_BEHAVIORS["supplier_b"],
                "required_fields": list(REQUIRED_FIELDS),
            },
        },
        {
            "id": "logistics",
            "kind": "organization",
            "attributes": {"safe_fallback_actions": SAFE_FALLBACKS["logistics"]},
            "action_space": {"schemas": {"allocate": ids["allocate"]}},
            "policy_id": "llm.v1",
            "policy_parameters": {
                "model": LLM_MODEL,
                "instructions": INSTRUCTIONS["logistics"],
                "behavior": ACTOR_BEHAVIORS["logistics"],
                "required_fields": list(REQUIRED_FIELDS),
            },
        },
    ]


def simulation_dict(experiment_id: str) -> dict[str, Any]:
    """Full SimulationConfig-compatible mapping for the candidate."""
    import copy

    ids = schema_ids(experiment_id)
    return {
        "world": {
            "actors": llm_actors(experiment_id),
            "parameters": copy.deepcopy(WORLD_PARAMETERS),
            "initial_public_state": copy.deepcopy(INITIAL_PUBLIC_STATE),
            "initial_private_state": {
                "manufacturer": {"facts": copy.deepcopy(MANUFACTURER_FACTS), "memory": {}},
                "supplier_a": {"facts": copy.deepcopy(SUPPLIER_FACTS), "memory": {}},
                "supplier_b": {"facts": copy.deepcopy(SUPPLIER_FACTS), "memory": {}},
                "logistics": {"facts": copy.deepcopy(LOGISTICS_FACTS), "memory": {}},
            },
        },
        "mechanism_id": ids["mechanism"],
        "protocol_id": "sequential.v1",
        "protocol_parameters": {"phases": schedule_phases(9)},
        "permissions": copy.deepcopy(PERMISSIONS),
        "max_steps": MAX_STEPS,
        "assumptions": copy.deepcopy(ASSUMPTIONS),
    }
