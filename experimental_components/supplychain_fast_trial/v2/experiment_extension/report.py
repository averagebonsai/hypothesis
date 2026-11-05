"""Offline preview and recorded-result notebooks for the flood experiment.

Preview uses only configuration/request: problem, disruption timeline,
physical sales ceiling, assumptions and limitations. The final report derives
every number from the recorded run and the resolved configuration; notebook
cells call shared rendering helpers and never repeat the simulation.
"""

from pathlib import Path
from typing import Any, cast

from experiment_extension.supplychain import Parameters, capacity_for_day, max_sellable_bound

from simulation_core.execution import JobManifest, JobResult
from simulation_core.reports import (
    ChartSeries,
    ReportFigure,
    ReportMarker,
    ReportNarrative,
    ReportPreview,
    assumption_prose,
    write_experiment_notebook,
    write_preview_notebook,
)

TITLE = "Decentralized supply-chain response to a flood disruption"


def _params(job: JobManifest) -> Parameters:
    return Parameters.from_json_values(job.simulation.world.parameters)


def _timeline(params: Parameters) -> tuple[list[int], list[int]]:
    days = list(range(1, params.horizon_days + 1))
    capacities = [capacity_for_day(params.capacity_schedule, day) for day in days]
    return days, capacities


def describe(job: JobManifest) -> ReportPreview:
    params = _params(job)
    days, capacities = _timeline(params)
    normal = max(capacities)
    disrupted_days = [d for d, c in zip(days, capacities) if c < normal]
    ceiling = max_sellable_bound(params)
    total_demand = params.horizon_days * params.daily_demand
    theory = (
        f"Transport capacity is {normal} component units/day normally and "
        f"{min(capacities)}/day on days {disrupted_days[0]}-{disrupted_days[-1]}. "
        f"Shipments arrive one day after dispatch. A rigorous physical ceiling on total "
        f"sales is {ceiling} units: demand allows {total_demand}, manufacturer capacity "
        f"allows {params.horizon_days * params.manufacturer_daily_capacity}, and component "
        f"availability caps each input line. This ceiling is a mathematical reference, not "
        f"a prediction of how the LLM actors will perform. No actor results exist yet."
    )
    return ReportPreview(
        title=TITLE,
        background=(
            "A finished product needs one unit of Component A and one of Component B. "
            "A manufacturer orders from two suppliers; a logistics provider ships both "
            "components under a shared daily capacity. A flood cuts capacity mid-horizon. "
            "Each organization sees only its own operations plus explicitly communicated "
            "orders, commitments and shipment notices (decentralized scenario)."
        ),
        rationale=(
            "The experiment asks how decentralized ordering, production and shipment "
            "choices respond to a visible capacity collapse and recovery, and which "
            "production, service, cost and recovery bottlenecks appear over nine days."
        ),
        theory=theory,
        assumptions=assumption_prose(job.simulation.assumptions),
        limitations=(
            (
                "Only the decentralized baseline runs once; no coordinated scenario or "
                "replication is tested, so no coordination or consistency claim is possible."
            ),
            (
                "A single nine-day trajectory cannot support general claims about how such "
                "organizations behave."
            ),
            (
                "Recorded actor explanations describe what actors reported, not independently "
                "verified motives."
            ),
        ),
    )


def preview(job: JobManifest, directory: Path) -> Path:
    return write_preview_notebook(directory, describe(job))


def _history(artifact: JobResult) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], artifact.result.final_state.public["history"])


def _cumulative_consolidated(history: list[dict[str, Any]], artifact: JobResult) -> list[float]:
    params = Parameters.from_json_values(artifact.manifest.simulation.world.parameters)
    cumulative: list[float] = []
    running = 0.0
    for record in history:
        revenue = params.finished_selling_price * record["sold"]
        costs = (
            params.supplier_unit_production_cost["supplier_a"] * record["produce_a"]
            + params.supplier_unit_production_cost["supplier_b"] * record["produce_b"]
            + params.assembly_unit_cost * record["mfg_produce"]
            + params.transport_unit_operating_cost * (record["alloc_a"] + record["alloc_b"])
        )
        holding_mfg = (
            params.manufacturer_component_holding_unit_cost * (record["mfg_a"] + record["mfg_b"])
            + params.finished_goods_holding_unit_cost * record["fg"]
        )
        holding_sup = params.supplier_holding_unit_cost * (
            record["sup_inv_a"] + record["sup_inv_b"]
        )
        running += revenue - costs - holding_mfg - holding_sup
        cumulative.append(running)
    return cumulative


def _recovery(history: list[dict], params: Parameters) -> str:
    horizon = params.horizon_days
    capacities = [capacity_for_day(params.capacity_schedule, d) for d in range(1, horizon + 1)]
    normal = max(capacities)
    restored = next(
        (
            d
            for d in range(1, horizon + 1)
            if capacities[d - 1] == normal and d > 1 and capacities[d - 2] < normal
        ),
        None,
    )
    if restored is None:
        return "No capacity restoration occurs within the horizon."
    streak_start = None
    for record in history:
        if record["day"] >= restored and record["lost"] == 0:
            if streak_start is None:
                streak_start = record["day"]
            if record["day"] - streak_start + 1 >= 3:
                lag = streak_start - restored
                return (
                    f"Stable fulfillment recovered: zero lost sales on days "
                    f"{streak_start}-{record['day']} (confirmed day {record['day']}; "
                    f"start lagged restoration on day {restored} by {lag} days)."
                )
        elif record["day"] >= restored:
            streak_start = None
    return (
        f"Recovery not observed within the horizon: no three consecutive zero-lost-sales "
        f"days after restoration on day {restored}. Later recovery is not extrapolated."
    )


def _actor_profits(artifact: JobResult) -> dict[str, float]:
    profits: dict[str, float] = {}
    for event in artifact.result.events:
        if event.outcome is None:
            continue
        for actor_id, value in event.outcome.payoffs.items():
            profits[actor_id] = profits.get(actor_id, 0.0) + value
    return profits


def report(artifact: JobResult, directory: Path) -> Path:
    params = Parameters.from_json_values(artifact.manifest.simulation.world.parameters)
    history = _history(artifact)
    days = [str(record["day"]) for record in history]
    cum_profit = _cumulative_consolidated(history, artifact)
    profits = _actor_profits(artifact)
    totals: dict[str, Any] = cast(dict[str, Any], artifact.result.final_state.public["totals"])
    ceiling = max_sellable_bound(params)
    recovery = _recovery(history, params)
    demand = [params.daily_demand] * len(history)

    figures = (
        ReportFigure(
            title="Daily sales versus customer demand",
            ylabel="Finished units",
            categories=tuple(days),
            series=(
                ChartSeries(label="Sold", values=tuple(float(r["sold"]) for r in history)),
                ChartSeries(label="Demand", values=tuple(float(v) for v in demand)),
            ),
            kind="bar",
        ),
        ReportFigure(
            title="Manufacturer component inventory",
            ylabel="Component units",
            categories=tuple(days),
            series=(
                ChartSeries(label="Component A", values=tuple(float(r["mfg_a"]) for r in history)),
                ChartSeries(label="Component B", values=tuple(float(r["mfg_b"]) for r in history)),
            ),
            kind="line",
            xlabel="Day",
            markers=(
                ReportMarker(category="3", label="flood onset", position="before"),
                ReportMarker(category="7", label="restoration", position="before"),
            ),
        ),
        ReportFigure(
            title="Transport utilization",
            ylabel="Component units",
            categories=tuple(days),
            series=(
                ChartSeries(
                    label="Dispatched",
                    values=tuple(float(r["alloc_a"] + r["alloc_b"]) for r in history),
                ),
                ChartSeries(label="Capacity", values=tuple(float(r["capacity"]) for r in history)),
            ),
            kind="line",
            xlabel="Day",
            markers=(
                ReportMarker(category="3", label="flood onset", position="before"),
                ReportMarker(category="7", label="restoration", position="before"),
            ),
        ),
        ReportFigure(
            title="Cumulative consolidated operating profit",
            ylabel="Currency units",
            categories=tuple(days),
            series=(ChartSeries(label="Consolidated profit", values=tuple(cum_profit)),),
            kind="line",
            xlabel="Day",
        ),
    )
    allocation_gap = sum(abs(r["alloc_a"] - r["alloc_b"]) for r in history)
    interpretation = (
        f"Over nine days the chain sold {totals['sold']} of {params.horizon_days * params.daily_demand} "
        f"demanded units ({totals['lost']} lost sales) for a consolidated operating profit of "
        f"{totals['consolidated']:g}. The physical sales ceiling is {ceiling} units, so the "
        f"shortfall reflects the flood disruption and the actors' decentralized responses, not "
        f"the demand limit alone. {recovery} Transport left "
        f"{sum(r['unused'] for r in history)} units of capacity unused while the A/B dispatch "
        f"gap summed to {allocation_gap} units, showing how the shared bottleneck split across "
        f"the two inputs. Per-actor profits were manufacturer {profits.get('manufacturer', 0.0):g}, "
        f"supplier A {profits.get('supplier_a', 0.0):g}, supplier B {profits.get('supplier_b', 0.0):g} "
        f"and logistics {profits.get('logistics', 0.0):g}; transfers cancel in the consolidated "
        f"figure. This describes one recorded trajectory only."
    )
    narrative = ReportNarrative(
        title=TITLE,
        background=(
            "A finished electronic product needs one unit of Component A (Supplier A) and one "
            "of Component B (Supplier B). Each day the manufacturer orders, suppliers produce "
            "and offer shipments, the logistics provider allocates shared transport, then the "
            "manufacturer builds and sells against daily demand of "
            f"{params.daily_demand} units. Shipments take one day. Capacity is "
            f"{max(r['capacity'] for r in history)} units/day except days 3-6, when the flood "
            f"cuts it to {min(r['capacity'] for r in history)}."
        ),
        rationale=(
            "Only the decentralized baseline runs: each organization decides from its own "
            "stock, orders and confirmations. Comparing sales, inventories, utilization and "
            "profit against the physical ceiling shows where the bottleneck bit. No "
            "coordinated scenario ran, so no coordination effect was tested."
        ),
        interpretation=interpretation,
        assumptions=assumption_prose(artifact.manifest.simulation.assumptions),
        limitations=(
            "One nine-day run cannot establish general behavioral findings.",
            (
                "No coordinated scenario or replication ran here; coordination and consistency "
                "claims remain untested."
            ),
            "Actor explanations are self-reports, not independent evidence of motives.",
            "The physical ceiling is a mathematical reference, not another scenario.",
        ),
    )
    return write_experiment_notebook(artifact, directory, narrative, figures=figures)
