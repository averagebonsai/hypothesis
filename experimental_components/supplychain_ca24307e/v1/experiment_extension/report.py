"""Preview and final notebooks for the flood-response supply-chain experiment.

All domain calculations live in this module's helpers and run before cells are
written; notebook cells only load the saved run and call the shared renderers.
"""

from pathlib import Path

from experiment_extension.bounds import physical_bounds
from experiment_extension.mechanism import capacity_for_day, normal_capacity
from experiment_extension.metrics import (
    RecoveryReport,
    audit_artifact,
    daily_records,
    fallback_decisions,
    recovery_report,
    restoration_day,
)
from experiment_extension.schemas import SupplyChainParameters

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

TITLE = "Decentralized supply-chain flood response over nine days"


def _parameters_for(manifest: JobManifest) -> SupplyChainParameters:
    return SupplyChainParameters.from_json_values(manifest.simulation.world.parameters)


def _timeline(params: SupplyChainParameters) -> tuple[str, int | None, int | None]:
    """Human timeline plus disruption start/restoration days derived from the schedule."""
    normal = normal_capacity(params)
    start: int | None = None
    restore: int | None = None
    for day in range(1, params.horizon_days + 1):
        if capacity_for_day(params, day) < normal and start is None:
            start = day
        if (
            start is not None
            and restore is None
            and capacity_for_day(params, day) >= normal
            and day > start
        ):
            restore = day
    if start is None:
        return f"Transport capacity stays at the normal {normal} units every day.", None, None
    text = (
        f"Transport capacity is {normal} units per day, drops to "
        f"{capacity_for_day(params, start)} during the flood starting on day {start}"
    )
    if restore is None:
        return text + " and never recovers within the horizon.", start, None
    return text + f", and is restored to {normal} on day {restore}.", start, restore


def describe(job: JobManifest) -> ReportPreview:
    params = _parameters_for(job)
    bounds = physical_bounds(job.simulation.world.parameters)
    timeline, flood_start, restore = _timeline(params)
    horizon = params.horizon_days
    background = (
        f"A manufacturer assembles finished electronic products from two components: A from "
        f"Supplier A and B from Supplier B. Each finished unit needs one of each, so production "
        f"stops when either component runs out. A shared logistics provider ships components with "
        f"a one-day transit delay, and a flood cuts its daily capacity mid-horizon. {timeline} "
        f"Customer demand is {params.daily_demand} finished units per day; unmet demand is lost "
        f"rather than backlogged. All four organizations are played by separate language-model "
        f"actors over one {horizon}-day trajectory."
    )
    rationale = (
        "Each actor sees only its own operations plus explicitly communicated orders, "
        "commitments, and shipment confirmations; nobody sees another organization's private "
        "stocks, costs, or simultaneous choices. Watching how these decentralized actors order, "
        "produce, and allocate through the disruption reveals where production, service, cost, "
        "and recovery bottlenecks emerge. This run is a decentralized baseline only: no "
        "coordinated scenario and no replications are executed, so no coordination comparison "
        "or consistency claim can be tested here."
    )
    streak = (
        f"Stable fulfillment means three consecutive days with zero lost sales starting on or "
        f"after restoration day {restore}."
        if restore is not None
        else "Capacity never recovers, so no post-restoration recovery streak can be assessed."
    )
    theory = (
        f"{timeline} {bounds.derivation} Procurement and freight charges are recognized when "
        f"components are dispatched, assembly when units are produced, and holding costs on "
        f"closing on-hand stock only. {streak} This preview shows the setup and the physical "
        f"bound only; no actor decisions have been observed and no performance interpretation "
        f"is possible yet."
    )
    _ = flood_start
    return ReportPreview(
        title=TITLE,
        background=background,
        rationale=rationale,
        theory=theory,
        assumptions=assumption_prose(job.simulation.assumptions),
        limitations=(
            "A single trajectory cannot establish general behavioral findings about how such actors behave.",
            "All prices, costs, capacities, and demand levels are hypothetical experimental values.",
            "Coordinated-versus-decentralized and replication comparisons are untested because only this baseline runs.",
            "The physical bound is a mathematical reference, not another scenario or a prediction of actor performance.",
            "Final-day dispatches remain in transit beyond the horizon, so closing stocks understate pipeline value.",
        ),
    )


def preview(job: JobManifest, directory: Path) -> Path:
    return write_preview_notebook(directory, describe(job))


def _figures(
    manifest: JobManifest, artifact: JobResult
) -> tuple[tuple[ReportFigure, ...], RecoveryReport, str]:
    params = _parameters_for(manifest)
    records = daily_records(artifact)
    categories = tuple(f"Day {record.day}" for record in records)
    flood_start: int | None = None
    normal = normal_capacity(params)
    for record in records:
        if record.capacity < normal:
            flood_start = record.day
            break
    restore = restoration_day(params)
    markers: list[ReportMarker] = []
    if flood_start is not None:
        markers.append(
            ReportMarker(
                category=f"Day {flood_start}",
                label=f"Flood onset (day {flood_start})",
                position="before",
            )
        )
    if restore is not None:
        markers.append(
            ReportMarker(
                category=f"Day {restore}", label=f"Recovery (day {restore})", position="before"
            )
        )
    marker_tuple = tuple(markers)
    sold = [float(record.sold) for record in records]
    lost = [float(record.lost_sales) for record in records]
    demand = [float(record.demand) for record in records]
    cumulative_sold: list[float] = []
    cumulative_demand: list[float] = []
    for index in range(len(records)):
        cumulative_sold.append(sum(sold[: index + 1]))
        cumulative_demand.append(sum(demand[: index + 1]))
    bounds = physical_bounds(manifest.simulation.world.parameters)
    bound_line = [float(bounds.overall_sales_bound)] * len(records)
    consolidated: list[float] = []
    maker: list[float] = []
    supplier_a: list[float] = []
    supplier_b: list[float] = []
    carrier: list[float] = []
    for index in range(len(records)):
        consolidated.append(sum(record.consolidated_profit for record in records[: index + 1]))
        maker.append(sum(record.manufacturer_profit for record in records[: index + 1]))
        supplier_a.append(sum(record.supplier_a_profit for record in records[: index + 1]))
        supplier_b.append(sum(record.supplier_b_profit for record in records[: index + 1]))
        carrier.append(sum(record.logistics_profit for record in records[: index + 1]))
    figures = (
        ReportFigure(
            title="Daily transport capacity",
            ylabel="Component units",
            categories=categories,
            series=(
                ChartSeries(
                    label="Capacity", values=tuple(float(record.capacity) for record in records)
                ),
            ),
            kind="bar",
            xlabel="Day",
            markers=marker_tuple,
        ),
        ReportFigure(
            title="Customer demand fulfillment",
            ylabel="Finished units",
            categories=categories,
            series=(
                ChartSeries(label="Units sold", values=tuple(sold)),
                ChartSeries(label="Lost sales", values=tuple(lost)),
            ),
            kind="bar",
            xlabel="Day",
            markers=marker_tuple,
        ),
        ReportFigure(
            title="Cumulative sales against the physical bound",
            ylabel="Finished units",
            categories=categories,
            series=(
                ChartSeries(label="Cumulative sold", values=tuple(cumulative_sold)),
                ChartSeries(label="Cumulative demand", values=tuple(cumulative_demand)),
                ChartSeries(
                    label=f"Physical bound ({bounds.overall_sales_bound})", values=tuple(bound_line)
                ),
            ),
            kind="line",
            xlabel="Day",
            markers=marker_tuple,
        ),
        ReportFigure(
            title="Manufacturer closing inventories",
            ylabel="Units",
            categories=categories,
            series=(
                ChartSeries(
                    label="Component A",
                    values=tuple(float(record.comp_a_closing) for record in records),
                ),
                ChartSeries(
                    label="Component B",
                    values=tuple(float(record.comp_b_closing) for record in records),
                ),
                ChartSeries(
                    label="Finished goods",
                    values=tuple(float(record.finished_closing) for record in records),
                ),
            ),
            kind="line",
            xlabel="Day",
            markers=marker_tuple,
        ),
        ReportFigure(
            title="Transport use",
            ylabel="Component units",
            categories=categories,
            series=(
                ChartSeries(
                    label="Dispatched",
                    values=tuple(
                        float(record.dispatched_a + record.dispatched_b) for record in records
                    ),
                ),
                ChartSeries(
                    label="Unused capacity",
                    values=tuple(float(record.unused_capacity) for record in records),
                ),
            ),
            kind="bar",
            xlabel="Day",
            markers=marker_tuple,
        ),
        ReportFigure(
            title="Cumulative profit",
            ylabel="Dollars",
            categories=categories,
            series=(
                ChartSeries(label="Consolidated", values=tuple(consolidated)),
                ChartSeries(label="Manufacturer", values=tuple(maker)),
                ChartSeries(label="Supplier A", values=tuple(supplier_a)),
                ChartSeries(label="Supplier B", values=tuple(supplier_b)),
                ChartSeries(label="Logistics", values=tuple(carrier)),
            ),
            kind="line",
            xlabel="Day",
            markers=marker_tuple,
        ),
    )
    recovery = recovery_report(
        [record.lost_sales for record in records], restore, params.horizon_days
    )
    return figures, recovery, bounds.derivation


def _interpretation(
    manifest: JobManifest, artifact: JobResult, recovery: RecoveryReport, derivation: str
) -> str:
    params = _parameters_for(manifest)
    records = daily_records(artifact)
    sold = sum(record.sold for record in records)
    lost = sum(record.lost_sales for record in records)
    consolidated = sum(record.consolidated_profit for record in records)
    maker = sum(record.manufacturer_profit for record in records)
    profit_a = sum(record.supplier_a_profit for record in records)
    profit_b = sum(record.supplier_b_profit for record in records)
    carrier = sum(record.logistics_profit for record in records)
    short_days = sum(1 for record in records if record.below_demand)
    normal = normal_capacity(params)
    flood = [record for record in records if record.capacity < normal]
    calm = [record for record in records if record.capacity >= normal]
    flood_use = sum(record.dispatched_a + record.dispatched_b for record in flood) / max(
        sum(record.capacity for record in flood), 1
    )
    unused = sum(record.unused_capacity for record in records)
    imbalance = max((record.imbalance for record in records), default=0)
    mean_imbalance = sum(record.imbalance for record in records) / max(len(records), 1)
    fallbacks = fallback_decisions(artifact)
    issues = audit_artifact(artifact, manifest.simulation.world.parameters)
    consistency = (
        "Independent recomputation from the recorded events confirms component conservation, "
        "transfer cancellation across the four organizations, lost-sales accounting, capacity "
        "limits, day-plus-one arrival timing, and backlog transitions on every day."
        if not issues
        else f"The independent audit flags {len(issues)} inconsistencies; treat the figures below accordingly."
    )
    bounds = physical_bounds(manifest.simulation.world.parameters)
    recovery_text = (
        f"{recovery.summary} Service stabilized quickly once capacity returned."
        if recovery.observed
        else f"{recovery.summary} Lost sales therefore still occur late in the horizon, so the "
        "pipeline lag outlasts the capacity restoration in this run."
    )
    calm_lost = sum(record.lost_sales for record in calm)
    flood_lost = sum(record.lost_sales for record in flood)
    return (
        f"Over {len(records)} days the chain sold {sold} of {sold + lost} demanded units, losing "
        f"{lost} sales ({flood_lost} during the flood window, {calm_lost} outside it). Consolidated "
        f"operating profit was ${consolidated:,.0f}, split into manufacturer ${maker:,.0f}, "
        f"Supplier A ${profit_a:,.0f}, Supplier B ${profit_b:,.0f}, and logistics ${carrier:,.0f}; "
        f"internal procurement and freight transfers cancel in the consolidated figure, which counts "
        f"only consumer revenue minus production, assembly, transport operating, and holding costs. "
        f"Production fell below daily demand on {short_days} days, transport ran at "
        f"{flood_use:.0%} of the reduced flood capacity with {unused} units of unused capacity in "
        f"total, and the largest daily A/B allocation imbalance was {imbalance} units "
        f"(mean {mean_imbalance:.1f}). {recovery_text} Against the physical reference "
        f"({derivation}) the run sold {sold} of at most {bounds.overall_sales_bound} feasible units, "
        f"losing {lost} against a minimum of {bounds.minimum_lost_sales}; the gap between observed "
        f"and bound reflects decentralized ordering, stock imbalances, and the flood's pipeline "
        f"lag rather than a coordination effect, which this single baseline cannot identify. "
        f"{fallbacks} of the recorded decisions used the exhausted-attempt safe fallback. "
        f"{consistency} This describes one recorded trajectory only; it does not establish how such "
        f"actors behave in general, and the actors' own recorded explanations are reports, not "
        f"independent evidence of their motives."
    )


def report(artifact: JobResult, directory: Path) -> Path:
    manifest = artifact.manifest
    preview_part = describe(manifest)
    figures, recovery, derivation = _figures(manifest, artifact)
    narrative = ReportNarrative(
        title=TITLE,
        background=preview_part.background,
        rationale=preview_part.rationale,
        interpretation=_interpretation(manifest, artifact, recovery, derivation),
        assumptions=preview_part.assumptions,
        limitations=preview_part.limitations,
    )
    return write_experiment_notebook(artifact, directory, narrative, figures=figures)
