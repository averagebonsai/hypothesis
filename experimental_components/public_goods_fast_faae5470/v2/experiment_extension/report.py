"""Preview and final notebooks for the withdrawal game.

Preview uses only configuration: problem definition, calculated theory,
assumptions, and limitations, with observed results explicitly pending.
The final report derives every number and figure from the recorded result
and the resolved configuration; notebook cells only render them.
"""

from pathlib import Path
from typing import Any

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
from simulation_core.types import Action


def _int(params: dict[str, JsonValue], key: str) -> int:
    return int(params[key])  # type: ignore[arg-type]


def _float(params: dict[str, JsonValue], key: str) -> float:
    return float(params[key])  # type: ignore[arg-type]


def _schedules(params: dict[str, JsonValue]) -> tuple[int, int, int, float, float]:
    return (
        _int(params, "participant_count"),
        _int(params, "rounds"),
        _int(params, "endowed_rounds"),
        _float(params, "endowment"),
        _float(params, "multiplier"),
    )


def build_preview(manifest: JobManifest) -> ReportPreview:
    count, rounds, endowed, endowment, multiplier = _schedules(
        dict(manifest.simulation.world.parameters)
    )
    actors = [actor.id for actor in manifest.simulation.world.actors]
    keep = marginal_private_return(multiplier, count)
    zero = zero_contribution_trajectory(count, rounds, endowed, endowment, multiplier)
    full = full_reinvestment_trajectory(count, rounds, endowed, endowment, multiplier)
    first_unendowed = endowed + 1
    return ReportPreview(
        title="Public goods with known endowment withdrawal",
        background=(
            f"{count} participants ({', '.join(actors)}) play {rounds} simultaneous "
            f"rounds of a public-goods game. A contribution is a voluntary payment into "
            f"a common pool; a round payoff is the round's gain or loss; saved wealth "
            f"accumulates those gains. Rounds 1-{endowed} pay each participant a fresh "
            f"endowment of {endowment:g}, rounds {first_unendowed}-{rounds} pay nothing, "
            "and the schedule is known to all from the outset. Each round, available "
            "funds are saved wealth plus that round's endowment, and any finite amount "
            "up to that is a legal contribution. After everyone commits, each "
            f"participant's payoff is endowment minus own contribution plus {multiplier:g} "
            f"times total contributions divided by {count}, added to savings. Completed "
            "rounds reveal everyone's contributions and payoffs; simultaneous "
            "uncommitted choices and others' private notes stay hidden."
        ),
        rationale=(
            "The question is how contributions adapt when a known endowment stops "
            "while savings remain spendable. Comparing the endowed phase against the "
            "post-withdrawal phase in one recorded trajectory shows the direction and "
            "size of that adaptation."
        ),
        theory=(
            f"Each contributed unit returns {keep:.4g} to its contributor through the "
            f"pool (multiplier {multiplier:g} divided by {count} participants). Because "
            "this marginal private return is below 1, a purely self-interested "
            "participant gains by withholding in any single round, whatever others do. "
            f"Withholding every round leaves {zero[-1].balance} per participant. Under "
            "the stronger finite-horizon assumptions (risk-neutral own-wealth "
            "maximizers with common knowledge of the known horizon), backward "
            "induction extends the one-round argument to every round, giving the "
            f"zero-contribution benchmark final wealth of {zero[-1].balance} each. By "
            f"contrast, full reinvestment of all available funds each round reaches "
            f"{full[-1].balance} per participant; it is a cooperative group-wealth "
            "reference for multiplier above 1, not a Nash equilibrium. These are "
            "mathematical references for interpreting the recording, not predictions "
            "of how the participants will behave."
        ),
        assumptions=assumption_prose(manifest.simulation.assumptions),
        limitations=(
            (
                "One trajectory with three participants has no statistical power and "
                "cannot establish a general behavioral finding."
            ),
            (
                "Without a control group, no causal treatment effect of withdrawal can "
                "be claimed; only the observed before/after change is reported."
            ),
            (
                "Actor explanations written during the run are self-reports, not "
                "independent evidence of motives."
            ),
        ),
    )


def preview(job: JobManifest, directory: Path) -> Path:
    return write_preview_notebook(directory, build_preview(job))


def _history(artifact: JobResult) -> list[dict[str, Any]]:
    raw = artifact.result.final_state.public.get("history")
    if not isinstance(raw, list):
        raise TypeError("Recorded result has no round history")
    records: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise TypeError("History records must be mappings")
        records.append(dict(item))
    return records


def _mapping(record: dict[str, Any], key: str) -> dict[str, Any]:
    value = record.get(key)
    if not isinstance(value, dict):
        raise TypeError(f"History record has no {key} mapping")
    return dict(value)


def _actor_ids(artifact: JobResult) -> list[str]:
    return [actor.id for actor in artifact.manifest.simulation.world.actors]


def build_figures(artifact: JobResult) -> tuple[ReportFigure, ...]:
    history = _history(artifact)
    actors = _actor_ids(artifact)
    _count, _rounds, endowed, _endowment, _multiplier = _schedules(
        dict(artifact.manifest.simulation.world.parameters)
    )
    categories = tuple(f"R{int(record['round'])}" for record in history)
    markers: tuple[ReportMarker, ...] = ()
    withdrawal_label = f"R{endowed + 1}"
    if withdrawal_label in categories:
        markers = (ReportMarker(category=withdrawal_label, label="withdrawal", position="before"),)
    contributions = ReportFigure(
        title="Contributions per round",
        ylabel="Contribution",
        xlabel="Round",
        categories=categories,
        series=tuple(
            ChartSeries(
                label=aid,
                values=tuple(float(_mapping(record, "contributions")[aid]) for record in history),
            )
            for aid in actors
        ),
        kind="line",
        markers=markers,
    )
    wealth = ReportFigure(
        title="Saved wealth per round",
        ylabel="Saved balance",
        xlabel="Round",
        categories=categories,
        series=tuple(
            ChartSeries(
                label=aid,
                values=tuple(float(_mapping(record, "balances")[aid]) for record in history),
            )
            for aid in actors
        ),
        kind="line",
        markers=markers,
    )
    return (contributions, wealth)


def build_references(artifact: JobResult) -> tuple[ReportReference, ...]:
    count, rounds, endowed, endowment, multiplier = _schedules(
        dict(artifact.manifest.simulation.world.parameters)
    )
    actors = _actor_ids(artifact)
    zero = zero_contribution_trajectory(count, rounds, endowed, endowment, multiplier)
    full = full_reinvestment_trajectory(count, rounds, endowed, endowment, multiplier)
    return (
        ReportReference(
            name="Zero-contribution benchmark",
            explanation=(
                "Self-interested Nash benchmark for the known finite horizon: "
                "contributing nothing every round. Its force comes from backward "
                "induction with common knowledge of the horizon and rational, risk-neutral "
                "own-wealth maximization when the multiplier divided by participant count is below one. It does not follow from the "
                "one-round incentive alone. Observed contributions above zero are a "
                "deviation toward the cooperative reference, not evidence against "
                "arithmetic."
            ),
            payoffs={aid: zero[-1].balance for aid in actors},
            payoff_basis="cumulative",
            actions=tuple(
                Action(
                    actor_id=aid, kind="contribute", payload={"contribution": zero[-1].contribution}
                )
                for aid in actors
            ),
        ),
        ReportReference(
            name="Cooperative full-reinvestment reference",
            explanation=(
                "Group-wealth reference when everyone reinvests all available funds "
                "each round; it is not a Nash equilibrium, and matching it would "
                "describe the observed outcome, not the participants' motives. This is an "
                "alternative complete history, not a feasible unilateral deviation from "
                "the observed final-round wealth. Group-wealth optimality requires a multiplier above one."
            ),
            payoffs={aid: full[-1].balance for aid in actors},
            payoff_basis="cumulative",
            actions=tuple(
                Action(
                    actor_id=aid, kind="contribute", payload={"contribution": full[-1].contribution}
                )
                for aid in actors
            ),
        ),
    )


def build_narrative(artifact: JobResult) -> ReportNarrative:
    params = dict(artifact.manifest.simulation.world.parameters)
    count, rounds, endowed, endowment, multiplier = _schedules(params)
    actors = _actor_ids(artifact)
    history = _history(artifact)
    keep = marginal_private_return(multiplier, count)
    zero = zero_contribution_trajectory(count, rounds, endowed, endowment, multiplier)
    full = full_reinvestment_trajectory(count, rounds, endowed, endowment, multiplier)

    def _total(records: list[dict[str, Any]]) -> float:
        return sum(
            float(value)
            for record in records
            for value in _mapping(record, "contributions").values()
        )

    early = [record for record in history if int(record["round"]) <= endowed]
    late = [record for record in history if int(record["round"]) > endowed]
    early_total = _total(early)
    late_total = _total(late)
    closing = _mapping(history[-1], "balances")
    finals = {aid: float(closing[aid]) for aid in actors}
    group_final = sum(finals.values())
    zero_group = count * zero[-1].balance
    full_group = count * full[-1].balance
    early_mean = early_total / (len(early) * count) if early else 0.0
    late_mean = late_total / (len(late) * count) if late else 0.0
    phase_text = (
        f"Contributions averaged {early_mean:.4g} per participant per endowed round "
        f"across {len(early)} rounds, and {late_mean:.4g} across {len(late)} rounds after withdrawal. "
        if early and late
        else "Only one endowment phase was observed, so a before/after comparison is unavailable. "
    )
    diverse = any(len(set(_mapping(record, "contributions").values())) > 1 for record in early)
    history_text = (
        "Participants' contributions had already diverged before withdrawal. " if diverse else ""
    )
    interpretation = (
        phase_text
        + history_text
        + f"The private return per contributed unit was {keep:.4g} in both phases; withdrawal "
        "changed fresh funding, not this marginal return. Saved balances remained spendable. "
        "Beliefs about reciprocity, accumulated wealth and the approaching final round also changed, "
        "so the fall in giving cannot uniquely be attributed to withdrawal. "
        f"The group ended with {group_final:.4g} in saved wealth, compared with {zero_group:g} "
        f"under all-zero giving and {full_group:g} under full reinvestment. These compare "
        "cumulative wealth across alternative complete histories, not a last-round deviation gain. "
        f"This is one {rounds}-round trajectory, not a general learned policy or a causal treatment estimate. "
        "The participants' own recorded explanations appear once in the next section and are self-reports."
    )
    return ReportNarrative(
        title="Public goods with known endowment withdrawal",
        background=(
            f"{count} participants ({', '.join(actors)}) play {rounds} simultaneous "
            "rounds. Each round every participant simultaneously chooses a "
            "contribution, any finite amount from nothing up to available funds "
            "(saved wealth plus that round's endowment). A round payoff is the "
            "round's gain or loss: endowment minus own contribution plus the pool "
            f"share ({multiplier:g} times total contributions divided by {count}); "
            "saved wealth is the running accumulation of payoffs and never "
            "decreases except through contributions that the pool does not repay. "
            f"Rounds 1-{endowed} endow {endowment:g} per participant and the remaining "
            f"rounds endow nothing, with the full schedule known from the start, so "
            "participants can plan for withdrawal. After each round everyone sees "
            "all contributions and payoffs; simultaneous uncommitted choices and "
            "others' private notes are never revealed. Each actor aims to maximize "
            "its own final saved balance with no assigned social preference."
        ),
        rationale=(
            "Withdrawal with spendable savings lets us observe giving when fresh funds stop. "
            "It does not isolate withdrawal from changing wealth, beliefs and the horizon. The "
            "endowed-phase versus post-withdrawal comparison, set against the "
            "zero-contribution and full-reinvestment references, shows which way "
            "and how far observed contributions move once the endowment stops."
        ),
        interpretation=interpretation,
        assumptions=tuple(
            dict.fromkeys(
                assumption_prose(
                    tuple(
                        item
                        for item in artifact.manifest.simulation.assumptions
                        if item.path
                        not in {
                            "/mechanism_id",
                            "/protocol_id",
                            "/max_steps",
                            "/protocol_parameters/rounds",
                        }
                    )
                )
            )
        ),
        limitations=(
            (
                f"A single {rounds}-round run with {count} participants cannot support general "
                "claims about LLM behavior; treat it as one observed trajectory."
            ),
            (
                "No control group ran alongside, so the before/after change cannot be "
                "called a causal treatment effect of withdrawal."
            ),
            (
                "LLM actors with conversation memory are not trained reinforcement "
                "learners, so the run cannot show a learned policy in that sense."
            ),
            (
                "Actor explanations describe what actors reported, not independently "
                "verified reasons for their choices."
            ),
        ),
    )


def report(artifact: JobResult, directory: Path) -> Path:
    return write_experiment_notebook(
        artifact,
        directory,
        build_narrative(artifact),
        references=build_references(artifact),
        figures=build_figures(artifact),
    )
