"""Decentralized nine-day supply-chain rules with flood disruption and settlement.

One finished unit needs one Component A (Supplier A) plus one Component B
(Supplier B). Each day runs four phases: manufacturer ordering, joint supplier
offers, logistics allocation, then manufacturer production with settlement.
Shipments arrive at the start of the next day. The mechanism owns legality,
transitions, accounting, and every actor's private operational facts; policies
cannot write private state in this experiment.
"""

from collections.abc import Iterable, Sequence
from copy import deepcopy
from typing import Any, TypeGuard

from experiment_extension.schemas import (
    AllocateAction,
    OrderAction,
    ProduceAction,
    SupplyAction,
    SupplyChainParameters,
)
from pydantic import BaseModel

from simulation_core.mechanism import Mechanism
from simulation_core.protocol import DecisionPhase
from simulation_core.types import (
    Action,
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
ACTOR_IDS = (MANUFACTURER, SUPPLIER_A, SUPPLIER_B, LOGISTICS)
SUPPLIER_OF = {"A": SUPPLIER_A, "B": SUPPLIER_B}
COMPONENT_OF_SUPPLIER = {SUPPLIER_A: "A", SUPPLIER_B: "B"}
STAGES = ("order", "supply", "ship", "settle")
TERMINAL_PHASE = "finished"

PUBLIC_INT_FIELDS = (
    "day",
    "capacity",
    "order_a",
    "order_b",
    "commit_a",
    "commit_b",
    "offer_a",
    "offer_b",
    "allocation_a",
    "allocation_b",
    "priority_mfg_a",
    "priority_mfg_b",
    "priority_sa",
    "priority_sb",
)
PUBLIC_PAIR_FIELDS = ("arrivals", "in_transit")
MANUFACTURER_FACTS = (
    "comp_a",
    "comp_b",
    "finished",
    "demand",
    "capacity",
    "backlog_a",
    "backlog_b",
    "selling_price",
    "price_a",
    "price_b",
    "assembly_cost",
    "freight_charge",
    "comp_holding_cost",
    "finished_holding_cost",
    "cumulative_revenue",
    "cumulative_cost",
    "cumulative_sold",
    "cumulative_lost_sales",
    "cumulative_produced",
    "history",
)
SUPPLIER_FACTS = (
    "component",
    "inventory",
    "capacity",
    "unit_cost",
    "sale_price",
    "holding_cost",
    "backlog",
    "produced_today",
    "cumulative_produced",
    "cumulative_dispatched",
    "cumulative_revenue",
    "cumulative_cost",
    "history",
)
LOGISTICS_FACTS = (
    "capacity",
    "charge",
    "operating_cost",
    "cumulative_dispatched",
    "cumulative_revenue",
    "cumulative_cost",
    "history",
)
MONEY_FACTS = frozenset(
    {
        "cumulative_revenue",
        "cumulative_cost",
        "unit_cost",
        "sale_price",
        "holding_cost",
        "selling_price",
        "price_a",
        "price_b",
        "assembly_cost",
        "freight_charge",
        "comp_holding_cost",
        "finished_holding_cost",
        "charge",
        "operating_cost",
    }
)
COUNT_FACTS = frozenset(
    {
        "comp_a",
        "comp_b",
        "finished",
        "demand",
        "capacity",
        "backlog_a",
        "backlog_b",
        "cumulative_sold",
        "cumulative_lost_sales",
        "cumulative_produced",
        "cumulative_dispatched",
        "inventory",
        "backlog",
        "produced_today",
    }
)


def capacity_for_day(params: SupplyChainParameters, day: int) -> int:
    for block in params.capacity_schedule:
        if block.start_day <= day <= block.end_day:
            return block.capacity
    raise ValueError(f"Day {day} is outside the capacity schedule")


def normal_capacity(params: SupplyChainParameters) -> int:
    return capacity_for_day(params, 1)


def parse_phase(phase: str) -> tuple[int, str] | None:
    """Return (day, stage) for decision phases, or None for the terminal phase."""
    if phase == TERMINAL_PHASE:
        return None
    if not phase.startswith("d"):
        raise ValueError(f"Unknown phase name: {phase}")
    day_text, _, stage = phase[1:].partition("_")
    if not day_text.isdigit() or stage not in STAGES:
        raise ValueError(f"Unknown phase name: {phase}")
    return int(day_text), stage


def expected_phase(tick: int, horizon: int) -> str:
    if tick == 4 * horizon:
        return TERMINAL_PHASE
    return f"d{tick // 4 + 1}_{STAGES[tick % 4]}"


def _is_int(value: Any) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_money(value: Any) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class SupplyChainMechanism(Mechanism):
    """Inventory, transit, capacity, demand, and settlement rules for the chain."""

    def required_action_schemas(self, config: WorldConfig) -> dict[str, dict[str, type[BaseModel]]]:
        return {
            MANUFACTURER: {"order": OrderAction, "produce": ProduceAction},
            SUPPLIER_A: {"supply": SupplyAction},
            SUPPLIER_B: {"supply": SupplyAction},
            LOGISTICS: {"allocate": AllocateAction},
        }

    def validate_config(self, config: WorldConfig) -> None:
        SupplyChainParameters.from_json_values(config.parameters)
        if {actor.id for actor in config.actors} != set(ACTOR_IDS):
            raise ValueError("This mechanism requires exactly the four chain roles")

    def validate_schedule(
        self, config: WorldConfig, stages: Iterable[DecisionPhase] | None
    ) -> None:
        if stages is None:
            return
        params = SupplyChainParameters.from_json_values(config.parameters)
        phases = list(stages)
        if len(phases) != 4 * params.horizon_days:
            raise ValueError("Schedule needs four phases per horizon day")
        for index, phase in enumerate(phases):
            day = index // 4 + 1
            stage = STAGES[index % 4]
            if phase.name != f"d{day}_{stage}":
                raise ValueError(f"Phase {index} must be d{day}_{stage}")
            expected = {
                "order": (MANUFACTURER,),
                "supply": (SUPPLIER_A, SUPPLIER_B),
                "ship": (LOGISTICS,),
                "settle": (MANUFACTURER,),
            }[stage]
            if set(phase.actor_ids) != set(expected) or len(phase.actor_ids) != len(expected):
                raise ValueError(f"Phase {phase.name} has the wrong actor set")

    def validate_state(self, config: WorldConfig, state: WorldState) -> None:
        params = SupplyChainParameters.from_json_values(config.parameters)
        horizon = params.horizon_days
        if state.tick > 4 * horizon:
            raise ValueError("State tick exceeds the horizon schedule")
        if state.phase != expected_phase(state.tick, horizon):
            raise ValueError("State phase disagrees with the day schedule")
        day = min(state.tick // 4 + 1, horizon)
        public = state.public
        if public.get("day") != day:
            raise ValueError("Public day disagrees with the tick")
        for field in PUBLIC_INT_FIELDS:
            value = public.get(field)
            if not _is_int(value) or value < 0:
                raise ValueError(f"Public field {field} must be a nonnegative integer")
        for field in PUBLIC_PAIR_FIELDS:
            value = public.get(field)
            if (
                not isinstance(value, dict)
                or set(value) != {"A", "B"}
                or any(not _is_int(amount) or amount < 0 for amount in value.values())
            ):
                raise ValueError(f"Public field {field} must map A/B to nonnegative integers")
        capacity = capacity_for_day(params, day)
        if public.get("capacity") != capacity:
            raise ValueError("Public capacity disagrees with the schedule")
        if public.get("disrupted") != (capacity < normal_capacity(params)):
            raise ValueError("Public disruption flag disagrees with the schedule")
        if set(state.private) != set(ACTOR_IDS):
            raise ValueError("Private state must cover exactly the four chain roles")
        if state.tick == 0:
            self._validate_initial(params, state)
        required = {
            MANUFACTURER: MANUFACTURER_FACTS,
            SUPPLIER_A: SUPPLIER_FACTS,
            SUPPLIER_B: SUPPLIER_FACTS,
            LOGISTICS: LOGISTICS_FACTS,
        }
        for actor_id, keys in required.items():
            facts = state.private[actor_id].facts
            if any(key not in facts for key in keys):
                raise ValueError(f"Private facts for {actor_id} are incomplete")
            for key in keys:
                value = facts[key]
                if key in COUNT_FACTS:
                    if not _is_int(value) or value < 0:
                        raise ValueError(
                            f"Private fact {actor_id}.{key} must be a nonnegative integer"
                        )
                elif key in MONEY_FACTS:
                    if not _is_money(value) or value < 0:
                        raise ValueError(f"Private fact {actor_id}.{key} must be nonnegative")
                elif key == "history":
                    if not isinstance(value, list):
                        raise ValueError(f"Private fact {actor_id}.history must be a list")
                elif key == "component":
                    expected = COMPONENT_OF_SUPPLIER[actor_id]
                    if value != expected:
                        raise ValueError(f"Private fact {actor_id}.component must be {expected}")

    def _validate_initial(self, params: SupplyChainParameters, state: WorldState) -> None:
        public = state.public
        for field in (
            "order_a",
            "order_b",
            "commit_a",
            "commit_b",
            "offer_a",
            "offer_b",
            "allocation_a",
            "allocation_b",
            "priority_mfg_a",
            "priority_mfg_b",
            "priority_sa",
            "priority_sb",
        ):
            if public.get(field) != 0:
                raise ValueError(f"Initial public field {field} must be zero")
        for field in PUBLIC_PAIR_FIELDS:
            if public.get(field) != {"A": 0, "B": 0}:
                raise ValueError(f"Initial public field {field} must be a zero pair")
        maker = state.private[MANUFACTURER].facts
        opening = params.initial_manufacturer_components
        if (
            maker.get("comp_a") != opening["A"]
            or maker.get("comp_b") != opening["B"]
            or maker.get("finished") != params.initial_finished_goods
            or maker.get("demand") != params.daily_demand
            or maker.get("capacity") != params.manufacturer_daily_capacity
        ):
            raise ValueError("Initial manufacturer facts disagree with the parameters")
        expected_terms = {
            "selling_price": params.finished_selling_price,
            "price_a": params.component_prices["A"],
            "price_b": params.component_prices["B"],
            "assembly_cost": params.assembly_unit_cost,
            "freight_charge": params.transport_unit_charge,
            "comp_holding_cost": params.manufacturer_component_holding_unit_cost,
            "finished_holding_cost": params.finished_goods_holding_unit_cost,
        }
        if any(maker.get(key) != value for key, value in expected_terms.items()):
            raise ValueError("Initial manufacturer terms disagree with the parameters")
        for actor_id in (SUPPLIER_A, SUPPLIER_B):
            facts = state.private[actor_id].facts
            if (
                facts.get("inventory") != params.initial_supplier_inventory[actor_id]
                or facts.get("capacity") != params.supplier_daily_capacity[actor_id]
                or facts.get("unit_cost") != params.supplier_unit_production_cost[actor_id]
            ):
                raise ValueError(f"Initial facts for {actor_id} disagree with the parameters")
            component = COMPONENT_OF_SUPPLIER[actor_id]
            if (
                facts.get("sale_price") != params.component_prices[component]
                or facts.get("holding_cost") != params.supplier_holding_unit_cost
            ):
                raise ValueError(f"Initial terms for {actor_id} disagree with the parameters")
        carrier = state.private[LOGISTICS].facts
        if (
            carrier.get("capacity") != capacity_for_day(params, 1)
            or carrier.get("charge") != params.transport_unit_charge
            or carrier.get("operating_cost") != params.transport_unit_operating_cost
        ):
            raise ValueError("Initial logistics facts disagree with the parameters")
        for actor_id in ACTOR_IDS:
            facts = state.private[actor_id].facts
            for key, value in facts.items():
                if (
                    key in COUNT_FACTS
                    and key
                    not in {"comp_a", "comp_b", "finished", "demand", "capacity", "inventory"}
                    and value != 0
                ):
                    raise ValueError(f"Initial counter {actor_id}.{key} must be zero")
                if (
                    key in MONEY_FACTS
                    and key
                    not in {
                        "unit_cost",
                        "sale_price",
                        "holding_cost",
                        "selling_price",
                        "price_a",
                        "price_b",
                        "assembly_cost",
                        "freight_charge",
                        "comp_holding_cost",
                        "finished_holding_cost",
                        "charge",
                        "operating_cost",
                    }
                    and value != 0
                ):
                    raise ValueError(f"Initial money {actor_id}.{key} must be zero")
            if facts.get("history") != []:
                raise ValueError(f"Initial history for {actor_id} must be empty")

    def validate_actions(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> None:
        parsed = parse_phase(state.phase)
        if parsed is None:
            raise ValueError("No actions are legal in the terminal phase")
        day, stage = parsed
        if day != state.public.get("day"):
            raise ValueError("Action phase disagrees with the current day")
        by_actor = {action.actor_id: action for action in actions}
        if len(by_actor) != len(actions):
            raise ValueError("Duplicate actions from one actor")
        if stage == "order":
            self._validate_order(by_actor)
        elif stage == "supply":
            self._validate_supply(state, by_actor)
        elif stage == "ship":
            self._validate_ship(state, by_actor)
        elif stage == "settle":
            self._validate_settle(state, by_actor)
        else:  # pragma: no cover - parse_phase restricts stages
            raise ValueError(f"Unknown stage: {stage}")

    def _validate_order(self, by_actor: dict[str, Action]) -> None:
        if set(by_actor) != {MANUFACTURER}:
            raise ValueError("Ordering phase needs exactly the manufacturer action")
        action = by_actor[MANUFACTURER]
        if action.kind != "order":
            raise ValueError("Manufacturer ordering phase needs kind 'order'")
        OrderAction.from_json_values(action.payload)

    def _validate_supply(self, state: WorldState, by_actor: dict[str, Action]) -> None:
        if set(by_actor) != {SUPPLIER_A, SUPPLIER_B}:
            raise ValueError("Supply phase needs exactly one action per supplier")
        for actor_id, action in by_actor.items():
            if action.kind != "supply":
                raise ValueError("Supply phase needs kind 'supply'")
            payload = SupplyAction.from_json_values(action.payload)
            facts = state.private[actor_id].facts
            capacity = facts["capacity"]
            backlog = facts["backlog"]
            inventory = facts["inventory"]
            assert _is_int(capacity) and _is_int(backlog) and _is_int(inventory)
            if payload.produce > capacity:
                raise ValueError(f"{actor_id} produces {payload.produce} above capacity {capacity}")
            if payload.fulfill > backlog:
                raise ValueError(f"{actor_id} accepts {payload.fulfill} above backlog {backlog}")
            if payload.ship_request > inventory + payload.produce:
                raise ValueError(
                    f"{actor_id} offers {payload.ship_request} above available stock "
                    f"{inventory + payload.produce}"
                )
            if payload.ship_request > payload.fulfill:
                raise ValueError(
                    f"{actor_id} offers {payload.ship_request} above accepted {payload.fulfill}"
                )

    def _validate_ship(self, state: WorldState, by_actor: dict[str, Action]) -> None:
        if set(by_actor) != {LOGISTICS}:
            raise ValueError("Shipping phase needs exactly the logistics action")
        action = by_actor[LOGISTICS]
        if action.kind != "allocate":
            raise ValueError("Shipping phase needs kind 'allocate'")
        payload = AllocateAction.from_json_values(action.payload)
        offer_a = state.public["offer_a"]
        offer_b = state.public["offer_b"]
        capacity = state.public["capacity"]
        assert _is_int(offer_a) and _is_int(offer_b) and _is_int(capacity)
        if payload.allocate_a > offer_a:
            raise ValueError(f"Allocation {payload.allocate_a} exceeds offer {offer_a} for A")
        if payload.allocate_b > offer_b:
            raise ValueError(f"Allocation {payload.allocate_b} exceeds offer {offer_b} for B")
        if payload.allocate_a + payload.allocate_b > capacity:
            raise ValueError(
                f"Allocation {payload.allocate_a + payload.allocate_b} exceeds capacity {capacity}"
            )
        for actor_id, component, allocated in (
            (SUPPLIER_A, "A", payload.allocate_a),
            (SUPPLIER_B, "B", payload.allocate_b),
        ):
            stock = state.private[actor_id].facts["inventory"]
            backlog = state.private[actor_id].facts["backlog"]
            assert _is_int(stock) and _is_int(backlog)
            if allocated > stock:
                raise ValueError(
                    f"Allocation {allocated} exceeds available stock {stock} for {component}"
                )
            if allocated > backlog:
                raise ValueError(
                    f"Allocation {allocated} exceeds outstanding backlog {backlog} for {component}"
                )

    def _validate_settle(self, state: WorldState, by_actor: dict[str, Action]) -> None:
        if set(by_actor) != {MANUFACTURER}:
            raise ValueError("Settlement phase needs exactly the manufacturer action")
        action = by_actor[MANUFACTURER]
        if action.kind != "produce":
            raise ValueError("Settlement phase needs kind 'produce'")
        payload = ProduceAction.from_json_values(action.payload)
        facts = state.private[MANUFACTURER].facts
        comp_a = facts["comp_a"]
        comp_b = facts["comp_b"]
        capacity = facts["capacity"]
        assert _is_int(comp_a) and _is_int(comp_b) and _is_int(capacity)
        limit = min(comp_a, comp_b, capacity)
        if payload.produce > limit:
            raise ValueError(f"Production {payload.produce} exceeds feasible {limit}")
        for actor_id, component, allocation_key in (
            (SUPPLIER_A, "A", "allocation_a"),
            (SUPPLIER_B, "B", "allocation_b"),
        ):
            allocated = state.public[allocation_key]
            stock = state.private[actor_id].facts["inventory"]
            supplier_backlog = state.private[actor_id].facts["backlog"]
            maker_backlog = facts["backlog_a" if component == "A" else "backlog_b"]
            assert (
                _is_int(allocated)
                and _is_int(stock)
                and _is_int(supplier_backlog)
                and _is_int(maker_backlog)
            )
            if allocated > stock:
                raise ValueError(
                    f"Dispatch {allocated} exceeds available stock {stock} for {component}"
                )
            if allocated > supplier_backlog or allocated > maker_backlog:
                raise ValueError(
                    f"Dispatch {allocated} exceeds outstanding backlog for {component}"
                )

    def evaluate(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> Outcome:
        self.validate_actions(config, state, actions)
        params = SupplyChainParameters.from_json_values(config.parameters)
        public = deepcopy(state.public)
        facts = {aid: deepcopy(item.facts) for aid, item in state.private.items()}
        return self._apply(params, public, facts, state.phase, actions)[2]

    def transition(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> TransitionResult:
        self.validate_actions(config, state, actions)
        params = SupplyChainParameters.from_json_values(config.parameters)
        public = deepcopy(state.public)
        facts = {aid: deepcopy(item.facts) for aid, item in state.private.items()}
        new_public, new_facts, outcome = self._apply(params, public, facts, state.phase, actions)
        private_updates = {
            actor_id: PrivateState(
                facts=new_facts[actor_id], memory=dict(state.private[actor_id].memory)
            )
            for actor_id in ACTOR_IDS
        }
        return TransitionResult(public=new_public, outcome=outcome, private_updates=private_updates)

    def _apply(
        self,
        params: SupplyChainParameters,
        public: dict[str, Any],
        facts: dict[str, dict[str, Any]],
        phase: str,
        actions: Sequence[Action],
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]], Outcome]:
        parsed = parse_phase(phase)
        assert parsed is not None
        day, stage = parsed
        by_actor = {action.actor_id: action for action in actions}
        if stage == "order":
            return self._apply_order(
                public, facts, day, OrderAction.from_json_values(by_actor[MANUFACTURER].payload)
            )
        if stage == "supply":
            payloads = {
                actor_id: SupplyAction.from_json_values(by_actor[actor_id].payload)
                for actor_id in (SUPPLIER_A, SUPPLIER_B)
            }
            return self._apply_supply(public, facts, day, payloads)
        if stage == "ship":
            return self._apply_ship(
                public, facts, day, AllocateAction.from_json_values(by_actor[LOGISTICS].payload)
            )
        return self._apply_settle(
            params,
            public,
            facts,
            day,
            ProduceAction.from_json_values(by_actor[MANUFACTURER].payload),
        )

    def _apply_order(
        self,
        public: dict[str, Any],
        facts: dict[str, dict[str, Any]],
        day: int,
        payload: OrderAction,
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]], Outcome]:
        # Prior-day shipments were already delivered into component stock by the
        # previous settlement, so the entering state is exactly what the
        # manufacturer observes when ordering. This phase only records orders.
        arrivals = public["arrivals"]
        assert isinstance(arrivals, dict)
        arrived_a = arrivals["A"]
        arrived_b = arrivals["B"]
        assert _is_int(arrived_a) and _is_int(arrived_b)
        maker = facts[MANUFACTURER]
        maker["backlog_a"] += payload.order_a
        maker["backlog_b"] += payload.order_b
        maker_history = maker["history"]
        assert isinstance(maker_history, list)
        maker_history.append(
            {
                "day": day,
                "order_a": payload.order_a,
                "order_b": payload.order_b,
                "arrived_a": arrived_a,
                "arrived_b": arrived_b,
            }
        )
        for component, ordered in (("A", payload.order_a), ("B", payload.order_b)):
            supplier = facts[SUPPLIER_OF[component]]
            supplier["backlog"] += ordered
            received = supplier["history"]
            assert isinstance(received, list)
            received.append({"day": day, "order_received": ordered})
        public["order_a"] = payload.order_a
        public["order_b"] = payload.order_b
        public["priority_mfg_a"] = payload.priority_a
        public["priority_mfg_b"] = payload.priority_b
        outcome = Outcome(
            payoffs={MANUFACTURER: 0.0},
            metrics={"day": day, "arrived_a": arrived_a, "arrived_b": arrived_b},
        )
        return public, facts, outcome

    def _apply_supply(
        self,
        public: dict[str, Any],
        facts: dict[str, dict[str, Any]],
        day: int,
        payloads: dict[str, SupplyAction],
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]], Outcome]:
        metrics: dict[str, Any] = {"day": day}
        for actor_id, payload in payloads.items():
            component = COMPONENT_OF_SUPPLIER[actor_id]
            supplier = facts[actor_id]
            supplier["inventory"] += payload.produce
            supplier["produced_today"] = payload.produce
            supplier["cumulative_produced"] += payload.produce
            history = supplier["history"]
            assert isinstance(history, list)
            history.append(
                {
                    "day": day,
                    "produce": payload.produce,
                    "fulfill": payload.fulfill,
                    "ship_request": payload.ship_request,
                    "priority": payload.priority,
                    "inventory": supplier["inventory"],
                }
            )
            public[f"commit_{component.lower()}"] = payload.fulfill
            public[f"offer_{component.lower()}"] = payload.ship_request
            public[f"priority_s{component.lower()}"] = payload.priority
            metrics[f"produced_{component.lower()}"] = payload.produce
            metrics[f"offered_{component.lower()}"] = payload.ship_request
        outcome = Outcome(payoffs={SUPPLIER_A: 0.0, SUPPLIER_B: 0.0}, metrics=metrics)
        return public, facts, outcome

    def _apply_ship(
        self,
        public: dict[str, Any],
        facts: dict[str, dict[str, Any]],
        day: int,
        payload: AllocateAction,
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]], Outcome]:
        public["allocation_a"] = payload.allocate_a
        public["allocation_b"] = payload.allocate_b
        carrier = facts[LOGISTICS]
        history = carrier["history"]
        assert isinstance(history, list)
        history.append(
            {
                "day": day,
                "allocate_a": payload.allocate_a,
                "allocate_b": payload.allocate_b,
                "offer_a": public["offer_a"],
                "offer_b": public["offer_b"],
                "capacity": public["capacity"],
            }
        )
        outcome = Outcome(
            payoffs={LOGISTICS: 0.0},
            metrics={
                "day": day,
                "allocated_a": payload.allocate_a,
                "allocated_b": payload.allocate_b,
            },
        )
        return public, facts, outcome

    def _apply_settle(
        self,
        params: SupplyChainParameters,
        public: dict[str, Any],
        facts: dict[str, dict[str, Any]],
        day: int,
        payload: ProduceAction,
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]], Outcome]:
        allocation_a = public["allocation_a"]
        allocation_b = public["allocation_b"]
        capacity = public["capacity"]
        assert _is_int(allocation_a) and _is_int(allocation_b) and _is_int(capacity)
        stock_a = facts[SUPPLIER_A]["inventory"]
        stock_b = facts[SUPPLIER_B]["inventory"]
        assert _is_int(stock_a) and _is_int(stock_b)
        # Validated actions guarantee allocations fit stock and backlogs; dispatch
        # exactly the allocation and reject any inconsistency instead of clamping.
        for allocated, stock, component in (
            (allocation_a, stock_a, "A"),
            (allocation_b, stock_b, "B"),
        ):
            if allocated > stock:
                raise ValueError(
                    f"Dispatch {allocated} exceeds available stock {stock} for {component}"
                )
        dispatched_a = allocation_a
        dispatched_b = allocation_b
        dispatched = dispatched_a + dispatched_b
        for dispatched_qty, key in (
            (dispatched_a, "backlog_a"),
            (dispatched_b, "backlog_b"),
        ):
            backlog = facts[MANUFACTURER][key]
            supplier_backlog = facts[SUPPLIER_OF["A" if key == "backlog_a" else "B"]]["backlog"]
            assert _is_int(backlog) and _is_int(supplier_backlog)
            if dispatched_qty > supplier_backlog or dispatched_qty > backlog:
                raise ValueError(
                    f"Dispatch {dispatched_qty} exceeds outstanding backlog for {key[-1]}"
                )
        produced_a = facts[SUPPLIER_A]["produced_today"]
        produced_b = facts[SUPPLIER_B]["produced_today"]
        assert _is_int(produced_a) and _is_int(produced_b)

        maker = facts[MANUFACTURER]
        quantity = payload.produce
        maker["comp_a"] -= quantity
        maker["comp_b"] -= quantity
        finished_available = maker["finished"] + quantity
        sold = min(finished_available, params.daily_demand)
        lost = params.daily_demand - sold
        maker["finished"] = finished_available - sold
        maker["backlog_a"] -= dispatched_a
        maker["backlog_b"] -= dispatched_b

        price_a = params.component_prices["A"]
        price_b = params.component_prices["B"]
        procurement = dispatched_a * price_a + dispatched_b * price_b
        assembly = quantity * params.assembly_unit_cost
        freight = dispatched * params.transport_unit_charge
        maker_holding = (
            maker["comp_a"] + maker["comp_b"]
        ) * params.manufacturer_component_holding_unit_cost
        finished_holding = maker["finished"] * params.finished_goods_holding_unit_cost
        maker_revenue = sold * params.finished_selling_price
        maker_cost = procurement + assembly + freight + maker_holding + finished_holding
        maker["cumulative_revenue"] += maker_revenue
        maker["cumulative_cost"] += maker_cost
        maker["cumulative_sold"] += sold
        maker["cumulative_lost_sales"] += lost
        maker["cumulative_produced"] += quantity
        maker_history = maker["history"]
        assert isinstance(maker_history, list)
        maker_history.append({"day": day, "produce": quantity, "sold": sold, "lost_sales": lost})

        supplier_profits: dict[str, float] = {}
        for actor_id, dispatched_qty, produced_qty, component in (
            (SUPPLIER_A, dispatched_a, produced_a, "A"),
            (SUPPLIER_B, dispatched_b, produced_b, "B"),
        ):
            supplier = facts[actor_id]
            supplier["inventory"] -= dispatched_qty
            supplier["backlog"] -= dispatched_qty
            supplier["cumulative_dispatched"] += dispatched_qty
            revenue = dispatched_qty * params.component_prices[component]
            cost = (
                produced_qty * params.supplier_unit_production_cost[actor_id]
                + supplier["inventory"] * params.supplier_holding_unit_cost
            )
            supplier["cumulative_revenue"] += revenue
            supplier["cumulative_cost"] += cost
            supplier_history = supplier["history"]
            assert isinstance(supplier_history, list)
            supplier_history.append({"day": day, "dispatched": dispatched_qty})
            supplier_profits[actor_id] = revenue - cost

        carrier = facts[LOGISTICS]
        carrier["cumulative_dispatched"] += dispatched
        carrier_revenue = dispatched * params.transport_unit_charge
        carrier_cost = dispatched * params.transport_unit_operating_cost
        carrier["cumulative_revenue"] += carrier_revenue
        carrier["cumulative_cost"] += carrier_cost
        carrier_history = carrier["history"]
        assert isinstance(carrier_history, list)
        carrier_history.append({"day": day, "dispatched": dispatched})

        # Closing costs and inventory are recorded above from pre-delivery stock.
        # Then prepare the next day: this day's dispatches arrive at the start of
        # the next day, so for days before the horizon they are delivered into
        # component stock now and the entering order observation already contains
        # them. Final-day dispatches stay in transit beyond the horizon.
        closing_a = maker["comp_a"]
        closing_b = maker["comp_b"]
        assert _is_int(closing_a) and _is_int(closing_b)
        next_day = min(day + 1, params.horizon_days)
        next_capacity = capacity_for_day(params, next_day)
        if day < params.horizon_days:
            maker["comp_a"] += dispatched_a
            maker["comp_b"] += dispatched_b
            public["arrivals"] = {"A": dispatched_a, "B": dispatched_b}
            public["in_transit"] = {"A": 0, "B": 0}
        else:
            public["in_transit"] = {"A": dispatched_a, "B": dispatched_b}
        public["day"] = next_day
        public["capacity"] = next_capacity
        public["disrupted"] = next_capacity < normal_capacity(params)
        carrier["capacity"] = next_capacity

        maker_profit = maker_revenue - maker_cost
        carrier_profit = carrier_revenue - carrier_cost
        consolidated = (
            maker_revenue
            - assembly
            - maker_holding
            - finished_holding
            - produced_a * params.supplier_unit_production_cost[SUPPLIER_A]
            - facts[SUPPLIER_A]["inventory"] * params.supplier_holding_unit_cost
            - produced_b * params.supplier_unit_production_cost[SUPPLIER_B]
            - facts[SUPPLIER_B]["inventory"] * params.supplier_holding_unit_cost
            - carrier_cost
        )
        outcome = Outcome(
            payoffs={
                MANUFACTURER: maker_profit,
                SUPPLIER_A: supplier_profits[SUPPLIER_A],
                SUPPLIER_B: supplier_profits[SUPPLIER_B],
                LOGISTICS: carrier_profit,
            },
            metrics={
                "day": day,
                "sold": sold,
                "lost_sales": lost,
                "demand": params.daily_demand,
                "produced": quantity,
                "finished_closing": maker["finished"],
                "comp_a_closing": closing_a,
                "comp_b_closing": closing_b,
                "dispatched_a": dispatched_a,
                "dispatched_b": dispatched_b,
                "offered_a": public["offer_a"],
                "offered_b": public["offer_b"],
                "fulfilled_a": public["commit_a"],
                "fulfilled_b": public["commit_b"],
                "allocated_a": allocation_a,
                "allocated_b": allocation_b,
                "capacity": capacity,
                "unused_capacity": capacity - dispatched,
                "supplier_a_inventory": facts[SUPPLIER_A]["inventory"],
                "supplier_b_inventory": facts[SUPPLIER_B]["inventory"],
                "supplier_a_produced": produced_a,
                "supplier_b_produced": produced_b,
                "manufacturer_profit": maker_profit,
                "supplier_a_profit": supplier_profits[SUPPLIER_A],
                "supplier_b_profit": supplier_profits[SUPPLIER_B],
                "logistics_profit": carrier_profit,
                "consolidated_profit": consolidated,
            },
        )
        return public, facts, outcome
