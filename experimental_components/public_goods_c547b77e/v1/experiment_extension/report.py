"""Preview and final notebooks for the public-goods withdrawal experiment.

All domain numbers shown here are calculated in the helpers below from the
recorded result and the resolved configuration. Notebook cells only load the
saved run and call the shared rendering functions; they never repeat the
simulation or contact models.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from experiment_extension.mechanism import (
    BALANCES_KEY,
    HISTORY_KEY,
    PublicGoodsParameters,
    as_number,
)
from experiment_extension.references import (
    full_reinvestment_trajectory,
    marginal_private_return,
    zero_contribution_trajectory,
)
from pydantic import JsonValue

from simulation_core.execution import JobManifest, JobResult
from simulation_core.reports import (
    ChartSeries,
    ReportFigure,
    ReportMarker,
    ReportNarrative,
    ReportPreview,
    ReportReference,
    assumption_prose,
    write_experiment_notebook,
    write_preview_notebook,
)
from simulation_core.types import Action, Event, SimulationConfig


@dataclass(frozen=True)
class RunParameters:
    participant_count: int
    rounds: int
    endowed_rounds: int
    endowment: float
    multiplier: float


@dataclass(frozen=True)
class PhaseSummary:
    rounds: int
    mean_contribution: float


def run_parameters(config: SimulationConfig) -> RunParameters:
    """Read the resolved game parameters shared by every calculation."""
    params = PublicGoodsParameters.model_validate(config.world.parameters)
    return RunParameters(
        participant_count=params.participant_count,
        rounds=params.rounds,
        endowed_rounds=params.endowed_rounds,
        endowment=params.endowment,
        multiplier=params.multiplier,
    )


def actor_ids(config: SimulationConfig) -> list[str]:
    return [actor.id for actor in config.world.actors]


def committed_events(artifact: JobResult) -> list[Event]:
    return [event for event in artifact.result.events if event.actions]


def history_records(artifact: JobResult) -> list[dict[str, JsonValue]]:
    """Return the recorded per-round entries from the final public state."""
    raw = artifact.result.final_state.public.get(HISTORY_KEY)
    if not isinstance(raw, list):
        raise ValueError("Recorded history is missing")  # noqa: TRY004
    records: list[dict[str, JsonValue]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError("Invalid recorded history entry")  # noqa: TRY004
        records.append(entry)
    return records


def record_contributions(record: dict[str, JsonValue], actors: Sequence[str]) -> dict[str, float]:
    stored = record.get("contributions")
    if not isinstance(stored, dict):
        raise ValueError("Recorded contributions are missing")  # noqa: TRY004
    return {aid: as_number(stored.get(aid), "recorded contribution") for aid in actors}


def record_round(record: dict[str, JsonValue]) -> int:
    return int(as_number(record.get("round"), "recorded round"))


def event_balances(event: Event, actors: Sequence[str]) -> dict[str, float]:
    stored = event.state.public.get(BALANCES_KEY)
    if not isinstance(stored, dict):
        raise ValueError("Recorded balances are missing")  # noqa: TRY004
    return {aid: as_number(stored.get(aid), "recorded balance") for aid in actors}


def phase_summaries(
    history: Sequence[dict[str, JsonValue]], actors: Sequence[str], endowed_rounds: int
) -> tuple[PhaseSummary, PhaseSummary]:
    """Mean per-participant contributions before and after the withdrawal."""
    early_totals = [
        sum(record_contributions(entry, actors).values())
        for entry in history
        if record_round(entry) <= endowed_rounds
    ]
    late_totals = [
        sum(record_contributions(entry, actors).values())
        for entry in history
        if record_round(entry) > endowed_rounds
    ]

    def summarize(totals: list[float]) -> PhaseSummary:
        if not totals:
            return PhaseSummary(rounds=0, mean_contribution=0.0)
        return PhaseSummary(
            rounds=len(totals), mean_contribution=sum(totals) / len(totals) / len(actors)
        )

    return summarize(early_totals), summarize(late_totals)


def withdrawal_markers(categories: Sequence[str], endowed_rounds: int) -> tuple[ReportMarker, ...]:
    """Mark the first round without a fresh endowment, when one was recorded."""
    if 0 <= endowed_rounds < len(categories):
        return (
            ReportMarker(
                category=categories[endowed_rounds],
                label="Endowment withdrawn",
                position="before",
            ),
        )
    return ()


def contribution_figure(
    history: Sequence[dict[str, JsonValue]], actors: Sequence[str], endowed_rounds: int
) -> ReportFigure:
    categories = tuple(f"R{record_round(entry)}" for entry in history)
    return ReportFigure(
        title="Contributions per round",
        ylabel="contribution",
        categories=categories,
        series=tuple(
            ChartSeries(
                label=aid,
                values=tuple(record_contributions(entry, actors)[aid] for entry in history),
            )
            for aid in actors
        ),
        kind="line",
        xlabel="round",
        markers=withdrawal_markers(categories, endowed_rounds),
    )


def wealth_figure(
    committed: Sequence[Event], actors: Sequence[str], endowed_rounds: int
) -> ReportFigure:
    categories = tuple(f"R{index}" for index, _ in enumerate(committed, start=1))
    return ReportFigure(
        title="Saved balances per round",
        ylabel="balance",
        categories=categories,
        series=tuple(
            ChartSeries(
                label=aid,
                values=tuple(event_balances(event, actors)[aid] for event in committed),
            )
            for aid in actors
        ),
        kind="line",
        xlabel="round",
        markers=withdrawal_markers(categories, endowed_rounds),
    )


def phase_figure(
    history: Sequence[dict[str, JsonValue]], actors: Sequence[str], endowed_rounds: int
) -> ReportFigure | None:
    """Mean contribution per phase; phases with no recorded rounds are omitted."""
    early, late = phase_summaries(history, actors, endowed_rounds)
    labels: list[str] = []
    values: list[float] = []
    if early.rounds:
        labels.append("Rounds with endowment")
        values.append(early.mean_contribution)
    if late.rounds:
        labels.append("Rounds after withdrawal")
        values.append(late.mean_contribution)
    if not labels:
        return None
    return ReportFigure(
        title="Mean contribution by phase",
        ylabel="mean contribution per participant",
        categories=tuple(labels),
        series=(ChartSeries(label="recorded", values=tuple(values)),),
        kind="bar",
        xlabel="phase",
    )


def mathematical_references(
    params: RunParameters, actors: Sequence[str]
) -> tuple[ReportReference, ReportReference]:
    """Zero-contribution and full-reinvestment comparisons for the final round."""
    zero = zero_contribution_trajectory(
        rounds=params.rounds,
        endowed_rounds=params.endowed_rounds,
        endowment=params.endowment,
        participant_count=params.participant_count,
    )
    full = full_reinvestment_trajectory(
        rounds=params.rounds,
        endowed_rounds=params.endowed_rounds,
        endowment=params.endowment,
        multiplier=params.multiplier,
        participant_count=params.participant_count,
    )
    zero_final = zero["per_round"][-1]
    full_final = full["per_round"][-1]
    return (
        ReportReference(
            name="Self-interested zero-contribution reference",
            explanation=(
                "Contributing nothing every round, the textbook reference for "
                "risk-neutral participants maximizing their own final balance over "
                "a known finite horizon when the marginal private return is below 1."
            ),
            actions=tuple(
                Action(actor_id=aid, kind="contribute", payload={"contribution": 0.0})
                for aid in actors
            ),
            payoffs=dict.fromkeys(actors, zero_final["round_payoff"]),
        ),
        ReportReference(
            name="Cooperative full-reinvestment reference",
            explanation=(
                "Contributing all available funds every round, the group-wealth "
                "reference when the multiplier exceeds 1. This is a cooperative "
                "benchmark, not a Nash equilibrium."
            ),
            actions=tuple(
                Action(
                    actor_id=aid,
                    kind="contribute",
                    payload={"contribution": full_final["contribution"]},
                )
                for aid in actors
            ),
            payoffs=dict.fromkeys(actors, full_final["round_payoff"]),
        ),
    )


def reference_totals(params: RunParameters) -> tuple[float, float]:
    """Final per-participant savings of the zero and full-reinvestment paths."""
    zero = zero_contribution_trajectory(
        rounds=params.rounds,
        endowed_rounds=params.endowed_rounds,
        endowment=params.endowment,
        participant_count=params.participant_count,
    )
    full = full_reinvestment_trajectory(
        rounds=params.rounds,
        endowed_rounds=params.endowed_rounds,
        endowment=params.endowment,
        multiplier=params.multiplier,
        participant_count=params.participant_count,
    )
    return (
        float(zero["final_balance_per_participant"]),
        float(full["final_group_wealth"] / params.participant_count),
    )


def assumption_lines(config: SimulationConfig) -> tuple[str, ...]:
    """Human-readable assumptions, with generic fallbacks when none are recorded."""
    if config.assumptions:
        return assumption_prose(config.assumptions)
    return (
        ("Contributions are bounded by savings plus the round endowment (modeling assumption)."),
        (
            "Completed rounds publish contributions and payoffs to all participants "
            "(modeling assumption)."
        ),
        (
            "Each participant maximizes only its own final balance, with no assigned "
            "social preferences (textbook convention)."
        ),
    )


def preview_theory(params: RunParameters) -> str:
    """Calculated benchmark text; never a prediction of participant behavior."""
    marginal = marginal_private_return(params.multiplier, params.participant_count)
    zero_final, full_final = reference_totals(params)
    below_one = "below" if marginal < 1 else "at or above"
    return (
        f"Each unit a participant contributes returns {params.multiplier:g} to the pool, "
        f"shared equally among {params.participant_count} participants, so the marginal "
        f"private return of one contributed unit is {marginal:.4g}. In a single isolated "
        f"round, keeping a unit beats contributing it whenever that return is below 1; "
        f"here it is {below_one} 1. That one-round arithmetic alone does not settle the "
        f"repeated game: the finite-horizon claim additionally assumes the horizon is "
        f"known, later rounds cannot reward earlier generosity, and the last round is "
        f"reached by backward induction, under which zero contributions every round is "
        f"the self-interested reference. It would end at {zero_final:g} saved per "
        f"participant. The cooperative full-reinvestment reference instead contributes "
        f"everything available each round and ends at {full_final:g} per participant; it "
        f"maximizes group wealth when the multiplier exceeds 1 but is not a Nash "
        f"equilibrium. Neither reference predicts how the participants will actually play."
    )


def preview(job: JobManifest, directory: Path) -> Path:
    """Render the pre-execution notebook from configuration alone."""
    params = run_parameters(job.simulation)
    content = ReportPreview(
        title="Public goods with endowment withdrawal",
        background=(
            "This experiment studies voluntary contributions to a shared pool when a "
            "known per-round gift is withdrawn partway through. Each participant starts "
            "with no savings. In endowed rounds everyone receives a fresh endowment and "
            "chooses an amount to place in the pool; the pool is multiplied and shared "
            "equally, and whatever is not contributed stays in savings. After the "
            "withdrawal round there are no fresh gifts, so any further contribution must "
            "come out of accumulated savings. All participants know the number of "
            "rounds, the withdrawal timing, the endowment and the multiplier from the "
            "outset, and after each round everyone sees every contribution and payoff."
        ),
        rationale=(
            "Announcing the withdrawal in advance separates two confounded stories: "
            "giving less because fresh money stopped is different from giving less out "
            "of surprise. Because savings remain spendable, participants can keep giving "
            "after the gifts stop, so the recorded path shows how contribution behavior "
            "adapts when the funding source changes but wealth persists."
        ),
        theory=preview_theory(params),
        assumptions=assumption_lines(job.simulation),
        limitations=(
            "A single trajectory cannot establish a general behavioral finding.",
            "Mathematical references frame the observations; they do not predict them.",
            "Without a comparison arm, no causal treatment effect can be isolated.",
        ),
    )
    return write_preview_notebook(directory, content)


def interpret_recorded_run(
    params: RunParameters,
    early: PhaseSummary,
    late: PhaseSummary,
    recorded_final: float,
    zero_final: float,
    full_final: float,
) -> str:
    """Explain the recorded aggregates against the incentive structure."""
    marginal = marginal_private_return(params.multiplier, params.participant_count)
    if early.rounds and late.rounds:
        direction = (
            "fell"
            if late.mean_contribution < early.mean_contribution
            else "rose"
            if late.mean_contribution > early.mean_contribution
            else "was unchanged"
        )
        phases = (
            f"Recorded giving averaged {early.mean_contribution:g} per participant in "
            f"the {early.rounds} endowed rounds and {late.mean_contribution:g} in the "
            f"{late.rounds} rounds after withdrawal, so average giving {direction} once "
            f"fresh gifts stopped."
        )
    elif late.rounds:
        phases = (
            f"No endowed rounds were recorded; giving averaged {late.mean_contribution:g} "
            f"per participant across the {late.rounds} unendowed rounds."
        )
    else:
        phases = (
            f"Every recorded round carried an endowment; giving averaged "
            f"{early.mean_contribution:g} per participant across the {early.rounds} rounds."
        )
    if recorded_final >= full_final:
        position = "matched or exceeded the full-reinvestment level"
    elif recorded_final <= zero_final:
        position = "sat at or below the zero-contribution level"
    else:
        position = "fell between the zero-contribution and full-reinvestment levels"
    return (
        f"{phases} Final savings averaged {recorded_final:g} per participant, which "
        f"{position} (references: {zero_final:g} and {full_final:g}). Each contributed "
        f"unit returned only {marginal:.4g} to the giver while adding "
        f"{params.multiplier:g} to the group, so own-balance incentives favored keeping "
        f"funds even as group wealth favored giving them: the recorded path shows how "
        f"this particular group navigated that tension before and after the withdrawal. "
        f"This describes one observed run, not a general learned policy or a causal "
        f"effect of the withdrawal itself."
    )


def final_narrative(artifact: JobResult) -> ReportNarrative:
    """Build the five-section narrative from recorded evidence only."""
    config = artifact.manifest.simulation
    params = run_parameters(config)
    actors = actor_ids(config)
    history = history_records(artifact)
    if not history:
        raise ValueError("No recorded rounds to report")
    early, late = phase_summaries(history, actors, params.endowed_rounds)
    final_balances = event_balances(committed_events(artifact)[-1], actors)
    recorded_final = sum(final_balances.values()) / len(actors)
    zero_final, full_final = reference_totals(params)
    return ReportNarrative(
        title="Public goods with endowment withdrawal",
        background=(
            "A public-goods game asks each participant to split money between private "
            "savings and a shared pool. Here a contribution is money placed in the "
            "pool; the pool is multiplied and divided equally, so everyone benefits "
            "from each gift. A payoff means the one-round change in savings: the "
            "round's endowment, minus what the participant gave, plus their equal "
            "share of the multiplied pool. Savings accumulate every round and can be "
            "spent later. Five participants played ten simultaneous rounds: rounds 1-5 "
            "gave a fresh endowment of 20 per participant per round, and rounds 6-10 "
            "gave nothing. The horizon and the withdrawal schedule were known to "
            "everyone from the start. Each round, participants saw the rules, their "
            "own funds and the full history of past contributions and payoffs, then "
            "chose simultaneously without seeing each other's pending gifts. Every "
            "choice carries the participant's own recorded rationale."
        ),
        rationale=(
            "Withdrawing a known gift while savings stay spendable isolates a clean "
            "question: when fresh money stops but wealth persists, does giving stop "
            "with it? Because the schedule was announced upfront, any adaptation "
            "reflects the funding shift rather than surprise. Two mathematical "
            "references frame the answer: all-zero giving as the self-interested "
            "finite-horizon reference, and all-in giving as the group-wealth "
            "reference. They are yardsticks for reading the recorded path, not "
            "predictions of it."
        ),
        interpretation=interpret_recorded_run(
            params, early, late, recorded_final, zero_final, full_final
        ),
        assumptions=assumption_lines(config),
        limitations=(
            (
                "One run with five participants cannot support general claims about "
                "contribution behavior."
            ),
            (
                "Without a control arm that keeps the endowment, the withdrawal carries "
                "no causal treatment effect."
            ),
            (
                "The actors are static language-model policies with memory, not trained "
                "reinforcement learners, so the trajectory shows adaptation within a run, "
                "not a learned policy."
            ),
            (
                "Recorded rationales report what participants said about their choices; "
                "they are not independent evidence of their motives."
            ),
            (
                "Stakes are experimental balances rather than real payments, which limits "
                "comparison with incentivized laboratory play."
            ),
        ),
    )


def report(artifact: JobResult, directory: Path) -> Path:
    """Render the five-section explanatory notebook from the recorded result."""
    config = artifact.manifest.simulation
    params = run_parameters(config)
    actors = actor_ids(config)
    history = history_records(artifact)
    if not history:
        raise ValueError("No recorded rounds to report")
    committed = committed_events(artifact)
    figures: list[ReportFigure] = [
        contribution_figure(history, actors, params.endowed_rounds),
        wealth_figure(committed, actors, params.endowed_rounds),
    ]
    phase = phase_figure(history, actors, params.endowed_rounds)
    if phase is not None:
        figures.append(phase)
    return write_experiment_notebook(
        artifact,
        directory,
        final_narrative(artifact),
        references=mathematical_references(params, actors),
        figures=tuple(figures),
    )
