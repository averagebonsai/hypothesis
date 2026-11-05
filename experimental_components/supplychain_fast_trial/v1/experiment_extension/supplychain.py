"""Supply-chain flood experiment: schemas, parameters and mechanism.

Nine days, four organizations (manufacturer, two suppliers, logistics
provider). Each day has four decision phases: manufacturer ordering, joint
supplier offers, logistics allocation, manufacturer production/settlement.
Transport capacity is 200 units/day on days 1-2 and 7-9 and 80 units/day on
days 3-6. Shipments have a one-day transit delay.
"""

from collections.abc import Sequence
from typing import Any, Literal, cast

from pydantic import BaseModel, Field, JsonValue

from simulation_core.mechanism import Mechanism
from simulation_core.types import (
    Action,
    FrozenModel,
    Outcome,
    PrivateState,
    TransitionResult,
    WorldConfig,
    WorldState,
)

MANUFACTURER = "manufacturer"
SUPPLIER_A = "supplier_a"
SUPPLIER_B = "supplier_b"
LOGISTICS = "logistics"

COMPONENTS = ("A", "B")
SUPPLIERS = (SUPPLIER_A, SUPPLIER_B)
COMPONENT_OF = {SUPPLIER_A: "A", SUPPLIER_B: "B"}


class Parameters(FrozenModel):
    horizon_days: int = Field(ge=1)
    capacity_schedule: tuple["CapacityWindow", ...] = Field(min_length=1)
    initial_manufacturer_components: dict[str, int]
    initial_supplier_inventory: dict[str, int]
    supplier_daily_capacity: dict[str, int]
    manufacturer_daily_capacity: int = Field(ge=0)
    daily_demand: int = Field(ge=0)
    initial_finished_goods: int = Field(ge=0)
    transit_days: int = Field(ge=1)
    finished_selling_price: float = Field(ge=0)
    component_prices: dict[str, float]
    supplier_unit_production_cost: dict[str, float]
    assembly_unit_cost: float = Field(ge=0)
    transport_unit_charge: float = Field(ge=0)
    transport_unit_operating_cost: float = Field(ge=0)
    manufacturer_component_holding_unit_cost: float = Field(ge=0)
    supplier_holding_unit_cost: float = Field(ge=0)
    finished_goods_holding_unit_cost: float = Field(ge=0)


class CapacityWindow(FrozenModel):
    start_day: int = Field(ge=1)
    end_day: int = Field(ge=1)
    capacity: int = Field(ge=0)


class OrderAction(FrozenModel):
    order_a: int = Field(ge=0)
    order_b: int = Field(ge=0)
    priority: Literal["none", "A", "B"] = "none"


class SupplierOffer(FrozenModel):
    produce: int = Field(ge=0)
    offer: int = Field(ge=0)
    priority_request: bool = False


class LogisticsAllocation(FrozenModel):
    alloc_a: int = Field(ge=0)
    alloc_b: int = Field(ge=0)


class MakeAction(FrozenModel):
    produce: int = Field(ge=0)


def capacity_for_day(schedule: Sequence[CapacityWindow] | Sequence[dict], day: int) -> int:
    """Transport capacity in force on a 1-based day; raises when uncovered."""
    for window in schedule:
        start = window["start_day"] if isinstance(window, dict) else window.start_day
        end = window["end_day"] if isinstance(window, dict) else window.end_day
        capacity = window["capacity"] if isinstance(window, dict) else window.capacity
        if start <= day <= end:
            return int(capacity)
    raise ValueError(f"No capacity window covers day {day}")


def phase_name(day: int, slot: str) -> str:
    return f"d{day}_{slot}"


def schedule_phases(horizon_days: int) -> list[dict[str, object]]:
    phases: list[dict[str, object]] = []
    for day in range(1, horizon_days + 1):
        phases.append({"name": phase_name(day, "order"), "actor_ids": [MANUFACTURER]})
        phases.append({"name": phase_name(day, "supply"), "actor_ids": [SUPPLIER_A, SUPPLIER_B]})
        phases.append({"name": phase_name(day, "ship"), "actor_ids": [LOGISTICS]})
        phases.append({"name": phase_name(day, "make"), "actor_ids": [MANUFACTURER]})
    return phases


def max_sellable_bound(parameters: Parameters) -> int:
    """Rigorous physical ceiling on total units sold over the horizon.

    Sales cannot exceed total demand, manufacturer production capacity, or
    component availability (initial manufacturer stock plus each supplier's
    initial stock and full-horizon production). Transport is ignored, so this
    is a ceiling, not a prediction.
    """
    demand_cap = parameters.horizon_days * parameters.daily_demand
    production_cap = parameters.horizon_days * parameters.manufacturer_daily_capacity
    component_caps = [
        parameters.initial_manufacturer_components[component]
        + parameters.initial_supplier_inventory[supplier]
        + parameters.horizon_days * parameters.supplier_daily_capacity[supplier]
        for supplier, component in ((SUPPLIER_A, "A"), (SUPPLIER_B, "B"))
    ]
    return int(min(demand_cap, production_cap, *component_caps))


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _private(state: WorldState, actor_id: str) -> dict[str, Any]:
    return dict(state.private[actor_id].facts)


def _int_dict(public: dict[str, JsonValue], key: str) -> dict[str, int]:
    return cast(dict[str, int], public[key])


def _int(public: dict[str, JsonValue], key: str) -> int:
    return cast(int, public[key])


def _records(public: dict[str, JsonValue], key: str) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], public[key])


class SupplyChainMechanism(Mechanism):
    """Decentralized flood-disruption supply chain with phased settlement."""

    def validate_config(self, config: WorldConfig) -> None:
        params = Parameters.from_json_values(config.parameters)
        if set(params.initial_manufacturer_components) != set(COMPONENTS):
            raise ValueError("Manufacturer components must cover A and B")
        if set(params.initial_supplier_inventory) != set(SUPPLIERS):
            raise ValueError("Supplier inventory must cover both suppliers")
        if set(params.supplier_daily_capacity) != set(SUPPLIERS):
            raise ValueError("Supplier capacity must cover both suppliers")
        if set(params.component_prices) != set(COMPONENTS):
            raise ValueError("Component prices must cover A and B")
        if set(params.supplier_unit_production_cost) != set(SUPPLIERS):
            raise ValueError("Supplier production costs must cover both suppliers")
        covered: set[int] = set()
        for window in params.capacity_schedule:
            if window.end_day < window.start_day:
                raise ValueError("Capacity window ends before it starts")
            covered.update(range(window.start_day, window.end_day + 1))
        if covered != set(range(1, params.horizon_days + 1)):
            raise ValueError("Capacity schedule must cover each horizon day exactly once")
        for value in (
            *params.initial_manufacturer_components.values(),
            *params.initial_supplier_inventory.values(),
            *params.supplier_daily_capacity.values(),
        ):
            if not _is_int(value) or value < 0:
                raise ValueError(
                    "Inventory and supplier capacity quantities must be nonnegative integers"
                )

    def required_action_schemas(self, config: WorldConfig) -> dict[str, dict[str, type[BaseModel]]]:
        return {
            MANUFACTURER: {"order": OrderAction, "produce": MakeAction},
            SUPPLIER_A: {"offer": SupplierOffer},
            SUPPLIER_B: {"offer": SupplierOffer},
            LOGISTICS: {"allocate": LogisticsAllocation},
        }

    def validate_state(self, config: WorldConfig, state: WorldState) -> None:
        params = Parameters.from_json_values(config.parameters)
        public = state.public
        for key in (
            "day",
            "capacity",
            "disrupted",
            "arrivals_today",
            "last_dispatch",
            "pending_offers",
            "backlogs",
            "in_transit",
            "history",
            "totals",
            "today",
        ):
            if key not in public:
                raise ValueError(f"Public state is missing {key}")
        day_value = _int(public, "day")
        if not 1 <= day_value <= params.horizon_days + 1:
            raise ValueError("Day is outside the horizon")
        for actor_id in (MANUFACTURER, SUPPLIER_A, SUPPLIER_B, LOGISTICS):
            if actor_id not in state.private:
                raise ValueError(f"Private state is missing {actor_id}")
        mfg = _private(state, MANUFACTURER)
        for key in ("comp_a", "comp_b", "finished_goods", "backlog_a", "backlog_b"):
            if mfg.get(key) is None or mfg[key] < 0:
                raise ValueError("Manufacturer stock or backlog is negative")
        for supplier in SUPPLIERS:
            facts = _private(state, supplier)
            if facts.get("inventory", -1) < 0 or facts.get("backlog", -1) < 0:
                raise ValueError("Supplier stock or backlog is negative")
        for entry in _records(public, "in_transit"):
            if entry["quantity"] < 0 or entry["arrival_day"] < public["day"]:
                raise ValueError("In-transit shipment is inconsistent with the current day")

    def _slot(self, state: WorldState) -> tuple[int, str]:
        name = state.phase
        day = int(name.split("_")[0][1:])
        slot = name.split("_", 1)[1]
        if slot not in ("order", "supply", "ship", "make"):
            raise ValueError(f"Unknown phase {name}")
        return day, slot

    def validate_actions(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> None:
        params = Parameters.from_json_values(config.parameters)
        day, slot = self._slot(state)
        public = state.public
        if slot == "order":
            if (
                len(actions) != 1
                or actions[0].actor_id != MANUFACTURER
                or actions[0].kind != "order"
            ):
                raise ValueError("Order phase needs one manufacturer order action")
            order_payload = OrderAction.model_validate(actions[0].payload)
            _ = (day, order_payload)
        elif slot == "supply":
            if len(actions) != 2 or {a.actor_id for a in actions} != {SUPPLIER_A, SUPPLIER_B}:
                raise ValueError("Supply phase needs one offer from each supplier")
            for action in actions:
                if action.kind != "offer":
                    raise ValueError("Supply phase accepts only offer actions")
                offer = SupplierOffer.model_validate(action.payload)
                facts = _private(state, action.actor_id)
                if offer.produce > params.supplier_daily_capacity[action.actor_id]:
                    raise ValueError("Supplier production exceeds daily capacity")
                if offer.offer > facts["backlog"]:
                    raise ValueError("Offer exceeds outstanding order backlog")
                if offer.offer > facts["inventory"] + offer.produce:
                    raise ValueError("Offer exceeds physically available stock")
        elif slot == "ship":
            if (
                len(actions) != 1
                or actions[0].actor_id != LOGISTICS
                or actions[0].kind != "allocate"
            ):
                raise ValueError("Ship phase needs one logistics allocation action")
            allocation = LogisticsAllocation.model_validate(actions[0].payload)
            offers = _int_dict(public, "pending_offers")
            if allocation.alloc_a > offers[SUPPLIER_A] or allocation.alloc_b > offers[SUPPLIER_B]:
                raise ValueError("Allocation exceeds submitted shipment offers")
            if allocation.alloc_a + allocation.alloc_b > _int(public, "capacity"):
                raise ValueError("Allocation exceeds daily transport capacity")
            inv_a = _private(state, SUPPLIER_A)["inventory"]
            inv_b = _private(state, SUPPLIER_B)["inventory"]
            if allocation.alloc_a > inv_a or allocation.alloc_b > inv_b:
                raise ValueError("Allocation exceeds physically available stock")
        elif slot == "make":
            if (
                len(actions) != 1
                or actions[0].actor_id != MANUFACTURER
                or actions[0].kind != "produce"
            ):
                raise ValueError("Make phase needs one manufacturer production action")
            build = MakeAction.model_validate(actions[0].payload)
            mfg = _private(state, MANUFACTURER)
            if build.produce > params.manufacturer_daily_capacity:
                raise ValueError("Production exceeds manufacturer daily capacity")
            if build.produce > mfg["comp_a"] or build.produce > mfg["comp_b"]:
                raise ValueError("Production exceeds available component inventory")

    def evaluate(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> Outcome:
        params = Parameters.from_json_values(config.parameters)
        day, slot = self._slot(state)
        payoffs = {MANUFACTURER: 0.0, SUPPLIER_A: 0.0, SUPPLIER_B: 0.0, LOGISTICS: 0.0}
        metrics: dict[str, JsonValue] = {"day": day, "slot": slot}
        if slot == "supply":
            for action in actions:
                offer = SupplierOffer.model_validate(action.payload)
                cost = params.supplier_unit_production_cost[action.actor_id] * offer.produce
                payoffs[action.actor_id] = -cost
                metrics[f"production_cost_{action.actor_id}"] = cost
        elif slot == "ship":
            allocation = LogisticsAllocation.model_validate(actions[0].payload)
            total = allocation.alloc_a + allocation.alloc_b
            payoffs[SUPPLIER_A] = params.component_prices["A"] * allocation.alloc_a
            payoffs[SUPPLIER_B] = params.component_prices["B"] * allocation.alloc_b
            procurement = (
                params.component_prices["A"] * allocation.alloc_a
                + params.component_prices["B"] * allocation.alloc_b
            )
            charge = params.transport_unit_charge * total
            payoffs[MANUFACTURER] = -(procurement + charge)
            payoffs[LOGISTICS] = charge - params.transport_unit_operating_cost * total
            metrics.update({"dispatched_a": allocation.alloc_a, "dispatched_b": allocation.alloc_b})
        elif slot == "make":
            build = MakeAction.model_validate(actions[0].payload)
            mfg = _private(state, MANUFACTURER)
            available = mfg["finished_goods"] + build.produce
            sold = min(params.daily_demand, available)
            payoffs[MANUFACTURER] = (
                params.finished_selling_price * sold
                - params.assembly_unit_cost * build.produce
                - params.manufacturer_component_holding_unit_cost
                * (mfg["comp_a"] - build.produce + mfg["comp_b"] - build.produce)
                - params.finished_goods_holding_unit_cost * (available - sold)
            )
            sup_a = _private(state, SUPPLIER_A)["inventory"]
            sup_b = _private(state, SUPPLIER_B)["inventory"]
            payoffs[SUPPLIER_A] = -params.supplier_holding_unit_cost * sup_a
            payoffs[SUPPLIER_B] = -params.supplier_holding_unit_cost * sup_b
            metrics.update({"sold": sold, "lost": params.daily_demand - sold})
        return Outcome(payoffs=payoffs, metrics=metrics)

    def transition(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> TransitionResult:
        self.validate_actions(config, state, actions)
        params = Parameters.from_json_values(config.parameters)
        day, slot = self._slot(state)
        public: dict[str, Any] = {key: _copy(value) for key, value in state.public.items()}
        facts: dict[str, dict[str, Any]] = {
            aid: _private(state, aid) for aid in (MANUFACTURER, SUPPLIER_A, SUPPLIER_B, LOGISTICS)
        }
        outcome = self.evaluate(config, state, actions)

        if slot == "order":
            order_payload = OrderAction.model_validate(actions[0].payload)
            facts[MANUFACTURER]["backlog_a"] += order_payload.order_a
            facts[MANUFACTURER]["backlog_b"] += order_payload.order_b
            facts[MANUFACTURER]["last_order_a"] = order_payload.order_a
            facts[MANUFACTURER]["last_order_b"] = order_payload.order_b
            facts[SUPPLIER_A]["backlog"] = facts[MANUFACTURER]["backlog_a"]
            facts[SUPPLIER_B]["backlog"] = facts[MANUFACTURER]["backlog_b"]
            facts[SUPPLIER_A]["last_order"] = order_payload.order_a
            facts[SUPPLIER_B]["last_order"] = order_payload.order_b
            public["backlogs"] = {
                SUPPLIER_A: facts[MANUFACTURER]["backlog_a"],
                SUPPLIER_B: facts[MANUFACTURER]["backlog_b"],
            }
            public["today"] = {
                "order_a": order_payload.order_a,
                "order_b": order_payload.order_b,
                "produce_a": 0,
                "produce_b": 0,
                "offer_a": 0,
                "offer_b": 0,
                "alloc_a": 0,
                "alloc_b": 0,
            }
        elif slot == "supply":
            for action in actions:
                offer = SupplierOffer.model_validate(action.payload)
                facts[action.actor_id]["inventory"] += offer.produce
                facts[action.actor_id]["cum_produced"] += offer.produce
                facts[action.actor_id]["cum_production_cost"] += (
                    params.supplier_unit_production_cost[action.actor_id] * offer.produce
                )
                facts[action.actor_id]["last_produce"] = offer.produce
                facts[action.actor_id]["last_offer"] = offer.offer
                facts[action.actor_id]["cum_offered"] += offer.offer
                public["pending_offers"][action.actor_id] = offer.offer
                public["today"]["produce_a" if action.actor_id == SUPPLIER_A else "produce_b"] = (
                    offer.produce
                )
                public["today"]["offer_a" if action.actor_id == SUPPLIER_A else "offer_b"] = (
                    offer.offer
                )
            facts[LOGISTICS]["request_a"] = public["pending_offers"][SUPPLIER_A]
            facts[LOGISTICS]["request_b"] = public["pending_offers"][SUPPLIER_B]
            facts[MANUFACTURER]["last_commit_a"] = public["pending_offers"][SUPPLIER_A]
            facts[MANUFACTURER]["last_commit_b"] = public["pending_offers"][SUPPLIER_B]
        elif slot == "ship":
            allocation = LogisticsAllocation.model_validate(actions[0].payload)
            total = allocation.alloc_a + allocation.alloc_b
            facts[SUPPLIER_A]["inventory"] -= allocation.alloc_a
            facts[SUPPLIER_B]["inventory"] -= allocation.alloc_b
            for supplier, alloc in (
                (SUPPLIER_A, allocation.alloc_a),
                (SUPPLIER_B, allocation.alloc_b),
            ):
                facts[supplier]["backlog"] -= alloc
                facts[supplier]["cum_dispatched"] += alloc
                facts[supplier]["cum_revenue"] += (
                    params.component_prices[COMPONENT_OF[supplier]] * alloc
                )
                facts[supplier]["last_dispatch"] = alloc
            facts[MANUFACTURER]["backlog_a"] -= allocation.alloc_a
            facts[MANUFACTURER]["backlog_b"] -= allocation.alloc_b
            facts[MANUFACTURER]["cum_procurement"] += (
                params.component_prices["A"] * allocation.alloc_a
                + params.component_prices["B"] * allocation.alloc_b
            )
            facts[MANUFACTURER]["cum_logistics"] += params.transport_unit_charge * total
            facts[MANUFACTURER]["last_dispatch_a"] = allocation.alloc_a
            facts[MANUFACTURER]["last_dispatch_b"] = allocation.alloc_b
            facts[LOGISTICS]["cum_dispatched"] += total
            facts[LOGISTICS]["cum_revenue"] += params.transport_unit_charge * total
            facts[LOGISTICS]["cum_operating"] += params.transport_unit_operating_cost * total
            facts[LOGISTICS]["cum_unused"] += public["capacity"] - total
            facts[LOGISTICS]["last_alloc_a"] = allocation.alloc_a
            facts[LOGISTICS]["last_alloc_b"] = allocation.alloc_b
            public["pending_offers"] = {SUPPLIER_A: 0, SUPPLIER_B: 0}
            public["backlogs"] = {
                SUPPLIER_A: facts[MANUFACTURER]["backlog_a"],
                SUPPLIER_B: facts[MANUFACTURER]["backlog_b"],
            }
            public["last_dispatch"] = {"A": allocation.alloc_a, "B": allocation.alloc_b}
            public["today"]["alloc_a"] = allocation.alloc_a
            public["today"]["alloc_b"] = allocation.alloc_b
            public["totals"]["dispatched"] += total
            if allocation.alloc_a:
                public["in_transit"].append(
                    {"component": "A", "quantity": allocation.alloc_a, "arrival_day": day + 1}
                )
            if allocation.alloc_b:
                public["in_transit"].append(
                    {"component": "B", "quantity": allocation.alloc_b, "arrival_day": day + 1}
                )
        elif slot == "make":
            build = MakeAction.model_validate(actions[0].payload)
            mfg = facts[MANUFACTURER]
            mfg["comp_a"] -= build.produce
            mfg["comp_b"] -= build.produce
            mfg["finished_goods"] += build.produce
            mfg["cum_assembly"] += params.assembly_unit_cost * build.produce
            sold = min(params.daily_demand, mfg["finished_goods"])
            lost = params.daily_demand - sold
            mfg["finished_goods"] -= sold
            mfg["cum_revenue"] += params.finished_selling_price * sold
            mfg["cum_sold"] += sold
            mfg["cum_lost"] += lost
            holding_mfg = (
                params.manufacturer_component_holding_unit_cost * (mfg["comp_a"] + mfg["comp_b"])
                + params.finished_goods_holding_unit_cost * mfg["finished_goods"]
            )
            mfg["cum_holding"] += holding_mfg
            holding_a = params.supplier_holding_unit_cost * facts[SUPPLIER_A]["inventory"]
            holding_b = params.supplier_holding_unit_cost * facts[SUPPLIER_B]["inventory"]
            facts[SUPPLIER_A]["cum_holding"] += holding_a
            facts[SUPPLIER_B]["cum_holding"] += holding_b
            mfg["last_produced"] = build.produce
            mfg["last_sold"] = sold
            mfg["last_lost"] = lost
            public["totals"]["sold"] += sold
            public["totals"]["lost"] += lost
            public["totals"]["produced_fg"] += build.produce
            public["totals"]["consumer_revenue"] += params.finished_selling_price * sold
            public["totals"]["assembly_cost"] += params.assembly_unit_cost * build.produce
            public["totals"]["transport_operating_cost"] += params.transport_unit_operating_cost * (
                public["today"]["alloc_a"] + public["today"]["alloc_b"]
            )
            public["totals"]["holding_cost"] += holding_mfg + holding_a + holding_b
            public["totals"]["supplier_production_cost"] += (
                params.supplier_unit_production_cost[SUPPLIER_A] * public["today"]["produce_a"]
                + params.supplier_unit_production_cost[SUPPLIER_B] * public["today"]["produce_b"]
            )
            public["history"].append(
                {
                    "day": day,
                    "capacity": public["capacity"],
                    "order_a": public["today"]["order_a"],
                    "order_b": public["today"]["order_b"],
                    "produce_a": public["today"]["produce_a"],
                    "produce_b": public["today"]["produce_b"],
                    "offer_a": public["today"]["offer_a"],
                    "offer_b": public["today"]["offer_b"],
                    "alloc_a": public["today"]["alloc_a"],
                    "alloc_b": public["today"]["alloc_b"],
                    "mfg_produce": build.produce,
                    "sold": sold,
                    "lost": lost,
                    "mfg_a": mfg["comp_a"],
                    "mfg_b": mfg["comp_b"],
                    "fg": mfg["finished_goods"],
                    "sup_inv_a": facts[SUPPLIER_A]["inventory"],
                    "sup_inv_b": facts[SUPPLIER_B]["inventory"],
                    "unused": public["capacity"]
                    - public["today"]["alloc_a"]
                    - public["today"]["alloc_b"],
                }
            )
            public["totals"]["consolidated"] = (
                public["totals"]["consumer_revenue"]
                - public["totals"]["supplier_production_cost"]
                - public["totals"]["assembly_cost"]
                - public["totals"]["transport_operating_cost"]
                - public["totals"]["holding_cost"]
            )
            # Close the day: credit shipments due next morning, then roll the clock.
            # Final-day dispatches remain in transit beyond the horizon.
            due = day + 1 if day < params.horizon_days else -1
            arriving = [s for s in public["in_transit"] if s["arrival_day"] == due]
            arrivals = {"A": 0, "B": 0}
            for shipment in arriving:
                arrivals[shipment["component"]] += shipment["quantity"]
            public["in_transit"] = [s for s in public["in_transit"] if s["arrival_day"] != due]
            mfg["comp_a"] += arrivals["A"]
            mfg["comp_b"] += arrivals["B"]
            mfg["last_arrivals_a"] = arrivals["A"]
            mfg["last_arrivals_b"] = arrivals["B"]
            public["arrivals_today"] = arrivals
            if day < params.horizon_days:
                public["day"] = day + 1
                public["capacity"] = capacity_for_day(params.capacity_schedule, day + 1)
                public["disrupted"] = public["capacity"] < max(
                    capacity_for_day(params.capacity_schedule, d)
                    for d in range(1, params.horizon_days + 1)
                )
            else:
                public["day"] = day + 1
            for actor_facts in facts.values():
                actor_facts["day"] = public["day"]

        private_updates = {aid: PrivateState(facts=facts[aid], memory={}) for aid in facts}
        return TransitionResult(public=public, outcome=outcome, private_updates=private_updates)


def _copy(value: object) -> object:
    if isinstance(value, dict):
        return {key: _copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy(item) for item in value]
    return value


Parameters.model_rebuild()
