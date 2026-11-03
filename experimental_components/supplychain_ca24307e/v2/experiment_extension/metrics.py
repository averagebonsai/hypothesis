"""Recorded-result analysis: daily series, recovery, and independent audits.

Every function here reads committed events, states, and outcome metrics from a
finished run plus the resolved parameters. Nothing calls the mechanism
transition, so the audits are independent recomputations rather than replays
of the execution helper.
"""

from math import isclose

from experiment_extension.mechanism import (
    MANUFACTURER,
    SUPPLIER_A,
    SUPPLIER_B,
    capacity_for_day,
    normal_capacity,
)
from experiment_extension.schemas import SupplyChainParameters
from pydantic import JsonValue

from simulation_core.execution import JobResult
from simulation_core.types import FrozenModel

_MONEY_TOLERANCE = 1e-6


class DayRecord(FrozenModel):
    day: int
    sold: int
    lost_sales: int
    demand: int
    produced: int
    finished_closing: int
    comp_a_closing: int
    comp_b_closing: int
    dispatched_a: int
    dispatched_b: int
    offered_a: int
    offered_b: int
    allocated_a: int
    allocated_b: int
    capacity: int
    unused_capacity: int
    imbalance: int
    below_demand: bool
    supplier_a_inventory: int
    supplier_b_inventory: int
    supplier_a_produced: int
    supplier_b_produced: int
    manufacturer_profit: float
    supplier_a_profit: float
    supplier_b_profit: float
    logistics_profit: float
    consolidated_profit: float


class RecoveryReport(FrozenModel):
    restoration_day: int | None
    streak_start: int | None
    confirmation_day: int | None
    lag_days: int | None
    observed: bool
    summary: str


def restoration_day(parameters: SupplyChainParameters) -> int | None:
    """First day capacity returns to normal after a disruption, if any."""
    normal = normal_capacity(parameters)
    disrupted = False
    for day in range(1, parameters.horizon_days + 1):
        capacity = capacity_for_day(parameters, day)
        if capacity < normal:
            disrupted = True
        elif disrupted and capacity >= normal:
            return day
    return None


def daily_records(artifact: JobResult) -> list[DayRecord]:
    """Settle-phase metrics in day order, with derived imbalance flags."""
    records = []
    for event in artifact.result.events:
        if not event.actions or event.outcome is None:
            continue
        metrics = event.outcome.metrics
        if event.actions[0].kind != "produce" or "sold" not in metrics:
            continue
        record = DayRecord.from_json_values(
            {
                **{key: metrics[key] for key in DayRecord.model_fields if key in metrics},
                "imbalance": abs(_as_int(metrics["allocated_a"]) - _as_int(metrics["allocated_b"])),
                "below_demand": bool(_as_int(metrics["produced"]) < _as_int(metrics["demand"])),
            }
        )
        records.append(record)
    records.sort(key=lambda item: item.day)
    return records


def recovery_report(
    lost_by_day: list[int], restoration: int | None, horizon: int
) -> RecoveryReport:
    """First three-day zero-lost-sales streak at/after restoration, else unobserved."""
    if restoration is None:
        return RecoveryReport(
            restoration_day=None,
            streak_start=None,
            confirmation_day=None,
            lag_days=None,
            observed=False,
            summary="No capacity restoration occurs within the horizon.",
        )
    for start in range(restoration, horizon - 1):
        window = lost_by_day[start - 1 : start + 2]
        if len(window) == 3 and all(value == 0 for value in window):
            lag = start - restoration
            return RecoveryReport(
                restoration_day=restoration,
                streak_start=start,
                confirmation_day=start + 2,
                lag_days=lag,
                observed=True,
                summary=(
                    f"Stable fulfillment starts on day {start}, confirmed on day {start + 2}, "
                    f"{lag} days after restoration on day {restoration}."
                ),
            )
    return RecoveryReport(
        restoration_day=restoration,
        streak_start=None,
        confirmation_day=None,
        lag_days=None,
        observed=False,
        summary=(
            f"Recovery not observed within the horizon: no three consecutive zero-lost-sales "
            f"days start on or after restoration day {restoration}."
        ),
    )


def _as_int(value: JsonValue) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"Expected an integer, found {value!r}")
    return value


def _as_float(value: JsonValue) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"Expected a number, found {value!r}")
    return float(value)


def audit_artifact(artifact: JobResult, parameters: dict[str, JsonValue]) -> tuple[str, ...]:
    """Recompute identities from recorded data; empty tuple means fully consistent."""
    params = SupplyChainParameters.from_json_values(parameters)
    issues: list[str] = []
    records = {record.day: record for record in daily_records(artifact)}
    horizon = params.horizon_days
    if sorted(records) != list(range(1, horizon + 1)):
        issues.append("Recorded settle days do not cover the horizon exactly once")
        return tuple(issues)

    settle_states = {}
    order_states = {}
    for event in artifact.result.events:
        if not event.actions:
            continue
        kind = event.actions[0].kind
        day_metric = event.outcome.metrics.get("day") if event.outcome else None
        if not isinstance(day_metric, int):
            continue
        if kind == "produce":
            settle_states[day_metric] = event.state
        elif kind == "order":
            order_states[day_metric] = event.state

    for day in range(1, horizon + 1):
        record = records[day]
        capacity = capacity_for_day(params, day)
        if record.capacity != capacity:
            issues.append(f"Day {day}: recorded capacity {record.capacity} != schedule {capacity}")
        if record.sold + record.lost_sales != record.demand:
            issues.append(f"Day {day}: sold + lost != demand")
        if record.dispatched_a + record.dispatched_b > record.capacity:
            issues.append(f"Day {day}: dispatches exceed transport capacity")
        if record.unused_capacity != record.capacity - record.dispatched_a - record.dispatched_b:
            issues.append(f"Day {day}: unused capacity identity fails")
        if record.dispatched_a > record.offered_a or record.dispatched_b > record.offered_b:
            issues.append(f"Day {day}: dispatches exceed supplier offers")
        if record.dispatched_a > record.allocated_a or record.dispatched_b > record.allocated_b:
            issues.append(f"Day {day}: dispatches exceed logistics allocation")
        actor_total = (
            record.manufacturer_profit
            + record.supplier_a_profit
            + record.supplier_b_profit
            + record.logistics_profit
        )
        if not isclose(actor_total, record.consolidated_profit, abs_tol=_MONEY_TOLERANCE):
            issues.append(f"Day {day}: actor profits do not sum to consolidated profit")
        # Post-settlement stock already contains the next day's arrivals for
        # days before the horizon; only the final day's state equals closing.
        delivered_a = record.dispatched_a if day < horizon else 0
        delivered_b = record.dispatched_b if day < horizon else 0
        maker = settle_states[day].private[MANUFACTURER].facts
        if _as_int(maker["comp_a"]) != record.comp_a_closing + delivered_a:
            issues.append(f"Day {day}: post-settlement Component A stock is inconsistent")
        if _as_int(maker["comp_b"]) != record.comp_b_closing + delivered_b:
            issues.append(f"Day {day}: post-settlement Component B stock is inconsistent")
        for actor_id, key, profit in (
            (SUPPLIER_A, "supplier_a_profit", record.supplier_a_profit),
            (SUPPLIER_B, "supplier_b_profit", record.supplier_b_profit),
        ):
            supplier = settle_states[day].private[actor_id].facts
            component = "A" if actor_id == SUPPLIER_A else "B"
            dispatched = record.dispatched_a if component == "A" else record.dispatched_b
            produced = (
                record.supplier_a_produced if component == "A" else record.supplier_b_produced
            )
            expected_revenue = dispatched * params.component_prices[component]
            expected_cost = (
                produced * params.supplier_unit_production_cost[actor_id]
                + _as_int(supplier["inventory"]) * params.supplier_holding_unit_cost
            )
            if not isclose(expected_revenue - expected_cost, profit, abs_tol=_MONEY_TOLERANCE):
                issues.append(f"Day {day}: {key} disagrees with recomputed cash flow")
        expected_log = (record.dispatched_a + record.dispatched_b) * (
            params.transport_unit_charge - params.transport_unit_operating_cost
        )
        if not isclose(expected_log, record.logistics_profit, abs_tol=_MONEY_TOLERANCE):
            issues.append(f"Day {day}: logistics profit disagrees with recomputed cash flow")
        expected_maker_revenue = record.sold * params.finished_selling_price
        expected_maker_cost = (
            record.dispatched_a * params.component_prices["A"]
            + record.dispatched_b * params.component_prices["B"]
            + record.produced * params.assembly_unit_cost
            + (record.dispatched_a + record.dispatched_b) * params.transport_unit_charge
            + (record.comp_a_closing + record.comp_b_closing)
            * params.manufacturer_component_holding_unit_cost
            + record.finished_closing * params.finished_goods_holding_unit_cost
        )
        if not isclose(
            expected_maker_revenue - expected_maker_cost,
            record.manufacturer_profit,
            abs_tol=_MONEY_TOLERANCE,
        ):
            issues.append(f"Day {day}: manufacturer profit disagrees with recomputed cash flow")

    consumed = 0
    for day in range(1, horizon + 1):
        record = records[day]
        consumed += record.produced
        produced_a = sum(records[d].supplier_a_produced for d in range(1, day + 1))
        produced_b = sum(records[d].supplier_b_produced for d in range(1, day + 1))
        state = settle_states[day]
        in_transit = state.public["in_transit"]
        if not isinstance(in_transit, dict):
            raise TypeError(f"Day {day}: in-transit stock is malformed")
        maker_state = state.private[MANUFACTURER].facts
        for component, supplier_id, produced_total, state_key in (
            ("A", SUPPLIER_A, produced_a, "comp_a"),
            ("B", SUPPLIER_B, produced_b, "comp_b"),
        ):
            supplier_stock = _as_int(state.private[supplier_id].facts["inventory"])
            maker_stock = _as_int(maker_state[state_key])
            pipeline = _as_int(in_transit[component])
            opening = (
                params.initial_supplier_inventory[supplier_id]
                + params.initial_manufacturer_components[component]
            )
            if supplier_stock + maker_stock + consumed + pipeline != opening + produced_total:
                issues.append(f"Day {day}: Component {component} conservation fails")

    for day in range(2, horizon + 1):
        arrivals = order_states[day].public["arrivals"]
        if not isinstance(arrivals, dict):
            raise TypeError(f"Day {day}: recorded arrivals are malformed")
        previous = records[day - 1]
        if (
            _as_int(arrivals["A"]) != previous.dispatched_a
            or _as_int(arrivals["B"]) != previous.dispatched_b
        ):
            issues.append(f"Day {day}: arrivals disagree with prior-day dispatches")
        # The ordering phase records orders only: component and finished stock
        # entering the order observation already equal the prior settlement.
        order_maker = order_states[day].private[MANUFACTURER].facts
        prior_maker = settle_states[day - 1].private[MANUFACTURER].facts
        for key in ("comp_a", "comp_b", "finished"):
            if _as_int(order_maker[key]) != _as_int(prior_maker[key]):
                issues.append(f"Day {day}: ordering-phase stock differs from prior settlement")
    final_transit = settle_states[horizon].public["in_transit"]
    if not isinstance(final_transit, dict):
        raise TypeError("Final in-transit stock is malformed")
    final_record = records[horizon]
    if (
        _as_int(final_transit["A"]) != final_record.dispatched_a
        or _as_int(final_transit["B"]) != final_record.dispatched_b
    ):
        issues.append("Final-day dispatches are not the recorded in-transit stock")

    for day in range(1, horizon + 1):
        state = settle_states[day]
        maker = state.private[MANUFACTURER].facts
        prior_maker = (
            artifact.result.events[0].state.private[MANUFACTURER].facts
            if day == 1
            else settle_states[day - 1].private[MANUFACTURER].facts
        )
        record = records[day]
        order_event = next(
            event
            for event in artifact.result.events
            if event.actions
            and event.actions[0].kind == "order"
            and event.outcome is not None
            and event.outcome.metrics.get("day") == day
        )
        for key, field, dispatched in (
            ("backlog_a", "order_a", record.dispatched_a),
            ("backlog_b", "order_b", record.dispatched_b),
        ):
            prior = _as_int(prior_maker[key])
            current = _as_int(maker[key])
            ordered_qty = _as_int(order_event.state.public[field])
            if current != prior + ordered_qty - dispatched or current < 0:
                issues.append(f"Day {day}: manufacturer {key} transition fails")
    return tuple(issues)


def fallback_decisions(artifact: JobResult) -> int:
    """Count recorded decisions that used the exhausted-attempt safe fallback."""
    return sum(
        1
        for event in artifact.result.events
        for decision in event.decisions
        if (decision.rationale or "").startswith("Safe fallback after")
    )
