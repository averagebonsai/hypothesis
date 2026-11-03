"""Preview and results notebook generators for the auction experiment."""

from math import isfinite
from pathlib import Path

from experiment_extension.auction import (
    AuctionParameters,
    BidPayload,
    TruthfulReference,
    truthful_reference,
)

from simulation_core.execution import JobManifest, JobResult
from simulation_core.reports import (
    ChartSeries,
    ReportFigure,
    ReportNarrative,
    ReportPreview,
    ReportReference,
    write_experiment_notebook,
    write_preview_notebook,
)
from simulation_core.types import Action, SimulationConfig

TITLE = "Sealed-bid second-price auction with LLM bidders"

SOURCE_LABELS = {
    "user": "user requirement",
    "textbook": "textbook convention",
    "model": "modeling choice",
    "default": "framework default",
}


def _fmt(value: float) -> str:
    return f"{value:g}"


def _order(config: SimulationConfig) -> tuple[str, ...]:
    return tuple(actor.id for actor in config.world.actors)


def _valuations(config: SimulationConfig) -> dict[str, float]:
    params = AuctionParameters.model_validate(config.world.parameters)
    valuations: dict[str, float] = {}
    for actor in config.world.actors:
        private = config.world.initial_private_state.get(actor.id)
        if private is None:
            raise ValueError(f"Missing private state for {actor.id}")
        value = private.facts.get(params.valuation_field)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            or value < 0
        ):
            raise ValueError(f"Invalid valuation for {actor.id}")
        valuations[actor.id] = float(value)
    return valuations


def _background() -> str:
    return (
        "This experiment studies bidding in a sealed-bid second-price auction, "
        "sometimes called a Vickrey auction. Each bidder privately values the same "
        "single indivisible item, submits one bid without seeing rival bids, and "
        "the highest bid wins while paying the second-highest submitted bid. "
        "A bidder's payoff, or utility, is their valuation minus the payment when "
        "they win, and zero otherwise; bidders are assumed risk-neutral, so they "
        "care about the expected payoff. A useful benchmark is truthful bidding, "
        "where every bidder bids exactly their valuation. Under independent "
        "private values with no reserve and no budget limits, truthful bidding is "
        "weakly dominant: no bidder can ever do strictly better by deviating, "
        "because a bid only affects whether one wins, never the price paid, which "
        "is set by rival bids. Bidding above one's valuation is still allowed and "
        "can backfire by winning at a price above value; bidding below value can "
        "give up a profitable win."
    )


def _rationale() -> str:
    return (
        "The question is how LLM bidders behave in this setting compared with the "
        "truthful benchmark. A single simultaneous round isolates bidding from "
        "learning, signaling, and reputation: each bidder acts once, from the "
        "public rules plus its own private valuation. Comparing actual bids with "
        "valuations, actual winner/payment/payoffs with the truthful reference, "
        "and reading the recorded decision rationales shows, for this run, "
        "whether the bidders bid truthfully, shade, or overbid, and what those "
        "choices cost or earned them."
    )


def _theory(valuations: dict[str, float], order: tuple[str, ...]) -> str:
    reference = truthful_reference(valuations, order)
    profile = ", ".join(f"{actor} {_fmt(valuations[actor])}" for actor in order)
    payoffs = ", ".join(f"{actor} {_fmt(reference.payoffs[actor])}" for actor in order)
    return (
        "Under independent private values with risk-neutral quasi-linear "
        "utility, one indivisible item, no reserve, and no budget constraints, "
        "bidding one's valuation is weakly dominant: whatever rivals bid, no "
        "unilateral deviation earns a strictly higher payoff than bidding value. "
        "The intuition is that the winner pays the second-highest bid, so "
        "raising your bid can only turn losses into wins priced above your "
        "value, and lowering it can only turn profitable wins into losses. "
        f"For the configured valuations ({profile}), the calculated "
        f"truthful-bidding reference is: bids equal valuations, winner "
        f"{reference.winner}, payment {_fmt(reference.payment)}, payoffs "
        f"({payoffs}). This reference is a theoretical comparison computed "
        "from the configuration. It is not a prediction of LLM behavior, it is "
        "not claimed to be the unique equilibrium, and a nontruthful bid is not "
        "automatically irrational."
    )


def _assumption_prose(config: SimulationConfig) -> tuple[str, ...]:
    if config.assumptions:
        lines = []
        for item in config.assumptions:
            label = SOURCE_LABELS.get(item.source, item.source)
            lines.append(f"{item.rationale} Configured value: {item.value} ({label}).")
        return tuple(lines)
    params = AuctionParameters.model_validate(config.world.parameters)
    return (
        (
            f"Independent private values ({params.value_model}); each bidder "
            "observes only its own valuation alongside the public rules."
        ),
        (
            f"Risk-neutral quasi-linear utility ({params.utility_model}): "
            "payoff is valuation minus payment when winning, zero otherwise."
        ),
        (
            f"No reserve price (reserve {params.reserve_price:g}): the highest "
            "bid always wins the item."
        ),
        f"No budget constraints ({params.budget_constraints}).",
        f"Highest-bid ties break by configuration order ({params.tie_break}).",
    )


def _limitation_prose(config: SimulationConfig, *, observed: bool) -> tuple[str, ...]:
    order = _order(config)
    scope = (
        f"One auction round with {len(order)} bidders and a single fixed "
        "valuation profile; the findings describe this run only."
    )
    lines = [scope]
    if observed:
        lines.append(
            "A single live execution: LLM decisions vary across runs, so one run "
            "cannot support a general behavioral finding about LLM bidders."
        )
    else:
        lines.append(
            "Observed LLM performance is pending: this preview contains only the "
            "problem definition and the calculated theoretical benchmark."
        )
    lines.extend(
        [
            (
                "The truthful reference is a weakly dominant strategy profile "
                "under the stated assumptions, not a complete equilibrium "
                "characterization or a prediction of behavior."
            ),
            (
                "Recorded decision rationales are the bidders' own explanations, "
                "not independent evidence about their motives."
            ),
            (
                "Sealed-bid privacy holds by construction through observation "
                "permissions, not through bidder choice."
            ),
        ]
    )
    return tuple(lines)


def preview(job: JobManifest, directory: Path) -> Path:
    config = job.simulation
    order = _order(config)
    valuations = _valuations(config)
    return write_preview_notebook(
        directory,
        ReportPreview(
            title=TITLE,
            background=_background(),
            rationale=_rationale(),
            theory=_theory(valuations, order),
            assumptions=_assumption_prose(config),
            limitations=_limitation_prose(config, observed=False),
        ),
    )


def _recorded_bids(artifact: JobResult) -> tuple[dict[str, float], dict[str, float]]:
    committed = [e for e in artifact.result.events if e.kind == "committed"]
    if not committed:
        raise ValueError("No committed rounds recorded")
    last = committed[-1]
    bids = {
        action.actor_id: BidPayload.model_validate(action.payload).bid for action in last.actions
    }
    if last.outcome is None:
        raise ValueError("Committed round lacks a recorded outcome")
    return bids, dict(last.outcome.payoffs)


def _recorded_clearing(artifact: JobResult) -> tuple[str, float]:
    committed = [e for e in artifact.result.events if e.kind == "committed"]
    if not committed or committed[-1].outcome is None:
        raise ValueError("No recorded outcome available")
    metrics = committed[-1].outcome.metrics
    winner = metrics.get("winner")
    payment = metrics.get("payment")
    if not isinstance(winner, str) or (
        isinstance(payment, bool) or not isinstance(payment, (int, float))
    ):
        raise TypeError("Recorded outcome lacks winner/payment metrics")
    return winner, float(payment)


def _interpretation(
    *,
    order: tuple[str, ...],
    valuations: dict[str, float],
    bids: dict[str, float],
    payoffs: dict[str, float],
    winner: str,
    payment: float,
    reference: TruthfulReference,
) -> str:
    bid_bits: list[str] = []
    for actor in order:
        gap = bids[actor] - valuations[actor]
        if gap == 0:
            relation = "exactly its valuation (truthful)"
        elif gap > 0:
            relation = f"{_fmt(gap)} above its valuation (overbidding)"
        else:
            relation = f"{_fmt(-gap)} below its valuation (underbidding)"
        bid_bits.append(
            f"{actor} bid {_fmt(bids[actor])} against a valuation of "
            f"{_fmt(valuations[actor])}, {relation}"
        )
    payoff_bits = ", ".join(f"{actor} {_fmt(payoffs[actor])}" for actor in order)
    first = (
        "Recorded bids: " + "; ".join(bid_bits) + ". "
        f"{winner} won and paid {_fmt(payment)}, the second-highest submitted "
        f"bid. Recorded payoffs: {payoff_bits}."
    )
    truthful_bidders = [a for a in order if bids[a] == valuations[a]]
    if len(truthful_bidders) == len(order):
        bid_sentence = "Every bidder bid truthfully."
    elif truthful_bidders:
        bid_sentence = (
            f"{', '.join(truthful_bidders)} bid truthfully while the other bidder(s) deviated."
        )
    else:
        bid_sentence = "No bidder bid exactly its valuation."
    if winner == reference.winner:
        winner_sentence = f"The actual winner matches the truthful winner ({winner})."
    else:
        winner_sentence = (
            f"The actual winner ({winner}) differs from the truthful winner "
            f"({reference.winner}): a deviation changed who won."
        )
    gap = payment - reference.payment
    if gap == 0:
        payment_sentence = f"The actual payment {_fmt(payment)} equals the truthful payment."
    elif gap > 0:
        payment_sentence = (
            f"The actual payment {_fmt(payment)} exceeds the truthful payment "
            f"{_fmt(reference.payment)} by {_fmt(gap)}."
        )
    else:
        payment_sentence = (
            f"The actual payment {_fmt(payment)} is {_fmt(-gap)} below the "
            f"truthful payment {_fmt(reference.payment)}."
        )
    second = (
        f"{bid_sentence} {winner_sentence} {payment_sentence} Because the "
        "winner pays the second-highest submitted bid, a deviation changes "
        "the payment only when it changes the top two bids."
    )
    third = (
        f"This describes one run with {len(order)} bidders and one valuation "
        "profile; it cannot support a general claim about LLM bidding. The "
        "bidders' own explanations appear once in the rationales section and "
        "are self-reports, not independent evidence about their motives."
    )
    return f"{first}\n\n{second}\n\n{third}"


def _reference(
    params: AuctionParameters,
    order: tuple[str, ...],
    reference: TruthfulReference,
) -> ReportReference:
    return ReportReference(
        name="Truthful bidding reference",
        explanation=(
            "Bids equal to private valuations with the second-price clearing "
            "rule applied. Truthfulness is weakly dominant under the stated "
            "assumptions; the comparison shows whether actual bids, winner, "
            "payment, and payoffs match or deviate from this profile, without "
            "claiming it is the unique equilibrium."
        ),
        actions=tuple(
            Action(
                actor_id=actor,
                kind=params.action_kind,
                payload={"bid": reference.bids[actor]},
            )
            for actor in order
        ),
        payoffs=dict(reference.payoffs),
    )


def _figures(
    order: tuple[str, ...],
    valuations: dict[str, float],
    bids: dict[str, float],
    payoffs: dict[str, float],
    reference: TruthfulReference,
) -> tuple[ReportFigure, ...]:
    return (
        ReportFigure(
            title="Bids versus private valuations",
            ylabel="Amount",
            categories=order,
            series=(
                ChartSeries(
                    label="Actual bid",
                    values=tuple(bids[actor] for actor in order),
                ),
                ChartSeries(
                    label="Valuation (truthful bid)",
                    values=tuple(valuations[actor] for actor in order),
                ),
            ),
        ),
        ReportFigure(
            title="Payoffs: actual versus truthful reference",
            ylabel="Payoff",
            categories=order,
            series=(
                ChartSeries(
                    label="Actual payoff",
                    values=tuple(payoffs[actor] for actor in order),
                ),
                ChartSeries(
                    label="Truthful reference payoff",
                    values=tuple(reference.payoffs[actor] for actor in order),
                ),
            ),
        ),
    )


def report(artifact: JobResult, directory: Path) -> Path:
    config = artifact.manifest.simulation
    params = AuctionParameters.model_validate(config.world.parameters)
    order = _order(config)
    valuations = _valuations(config)
    reference = truthful_reference(valuations, order)
    bids, payoffs = _recorded_bids(artifact)
    winner, payment = _recorded_clearing(artifact)
    narrative = ReportNarrative(
        title=TITLE,
        background=_background(),
        rationale=_rationale(),
        interpretation=_interpretation(
            order=order,
            valuations=valuations,
            bids=bids,
            payoffs=payoffs,
            winner=winner,
            payment=payment,
            reference=reference,
        ),
        assumptions=_assumption_prose(config),
        limitations=_limitation_prose(config, observed=True),
    )
    return write_experiment_notebook(
        artifact,
        directory,
        narrative,
        references=(_reference(params, order, reference),),
        figures=_figures(order, valuations, bids, payoffs, reference),
    )
