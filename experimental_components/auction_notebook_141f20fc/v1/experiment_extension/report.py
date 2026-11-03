"""Explanatory results notebook for the sealed-bid second-price auction."""

from pathlib import Path

from experiment_extension.reference import truthful_second_price
from pydantic import JsonValue

from simulation_core.execution import JobResult
from simulation_core.reports import (
    ChartSeries,
    ReportFigure,
    ReportNarrative,
    ReportReference,
    write_experiment_notebook,
)
from simulation_core.types import Action


def _number(value: JsonValue, *, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{what} is not a number: {value!r}")  # noqa: TRY004
    return float(value)


def _describe_amount(value: JsonValue) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "not recorded"
    return f"{float(value):g}"


def generate_auction_notebook(artifact: JobResult, output_directory: Path) -> Path:
    """Compare recorded LLM bids with valuations and the truthful reference."""
    committed = [
        event for event in artifact.result.events if event.kind == "committed" and event.actions
    ]
    if not committed:
        raise ValueError("Notebook generation requires at least one committed bidder decision")
    config = artifact.manifest.simulation
    order = [actor.id for actor in config.world.actors]
    if len(order) < 2:
        raise ValueError("Notebook generation requires at least two bidders")
    event = committed[-1]
    if event.outcome is None:
        raise ValueError("Latest committed profile has no recorded outcome")
    bids: dict[str, float] = {}
    for action in event.actions:
        bids[action.actor_id] = _number(
            action.payload.get("bid"), what=f"Recorded bid for {action.actor_id}"
        )
    if set(bids) != set(order):
        raise ValueError("Recorded bids do not cover every bidder")
    valuations: dict[str, float] = {}
    for aid in order:
        private = config.world.initial_private_state.get(aid)
        if private is None or "valuation" not in private.facts:
            raise ValueError(f"No recorded valuation for bidder {aid}")
        valuations[aid] = _number(private.facts["valuation"], what=f"Valuation for {aid}")
    outcome = event.outcome
    if set(outcome.payoffs) != set(order):
        raise ValueError("Recorded payoffs do not cover every bidder")
    actual_payoffs = {aid: float(outcome.payoffs[aid]) for aid in order}
    reference = truthful_second_price(valuations, tuple(order))
    raw_kind = config.world.parameters.get("action_kind", "submit_bid")
    action_kind = raw_kind if isinstance(raw_kind, str) and raw_kind else "submit_bid"

    comparison = ReportReference(
        name="Truthful-bidding reference",
        explanation=(
            "The settlement that would result if every bidder bid exactly their own "
            "private valuation. Under independent private values with risk-neutral "
            "quasi-linear utility, bidding truthfully is a weakly dominant strategy: "
            "no other bid ever pays more, whatever the others bid. This is a "
            "separately calculated point comparison, not an equilibrium solution, and "
            "a deviation from it does not by itself prove a bid was irrational."
        ),
        actions=tuple(
            Action(actor_id=aid, kind=action_kind, payload={"bid": reference.bids[aid]})
            for aid in order
        ),
        payoffs=dict(reference.payoffs),
        source_ticks={},
    )
    bid_figure = ReportFigure(
        title="Bids versus private valuations",
        ylabel="Amount",
        categories=tuple(order),
        series=(
            ChartSeries(label="Bids", values=tuple(bids[aid] for aid in order)),
            ChartSeries(label="Valuations", values=tuple(valuations[aid] for aid in order)),
        ),
    )
    payoff_figure = ReportFigure(
        title="Actual versus truthful payoffs",
        ylabel="Payoff",
        categories=tuple(order),
        series=(
            ChartSeries(label="Actual payoff", values=tuple(actual_payoffs[aid] for aid in order)),
            ChartSeries(
                label="Truthful payoff",
                values=tuple(reference.payoffs[aid] for aid in order),
            ),
        ),
    )

    recorded_winner = outcome.metrics.get("winner")
    winner_text = recorded_winner if isinstance(recorded_winner, str) else "not recorded"
    payment_text = _describe_amount(outcome.metrics.get("payment"))
    bid_lines = ", ".join(
        f"{aid} bid {bids[aid]:g} (valuation {valuations[aid]:g})" for aid in order
    )
    payoff_lines = ", ".join(f"{aid}: {actual_payoffs[aid]:g}" for aid in order)
    reference_lines = ", ".join(f"{aid}: {reference.payoffs[aid]:g}" for aid in order)
    order_text = ", then ".join(order)
    if winner_text == reference.winner and payment_text == f"{reference.payment:g}":
        match_text = (
            f"The recorded winner and payment match the truthful reference: {winner_text} "
            f"would also win under truthful bidding and pay {payment_text}. A match means "
            "the auction outcome coincides with the textbook benchmark on this run; it "
            "does not show that every bid was truthful or that LLM bidders always "
            "behave this way."
        )
    else:
        match_text = (
            f"The recorded outcome differs from the truthful reference, where "
            f"{reference.winner} would win and pay {reference.payment:g}. A deviation "
            "means the recorded bids led somewhere other than the textbook benchmark "
            "on this run; it does not by itself prove any bid was irrational, since "
            "truthful bidding is only weakly dominant and many motives can shape a "
            "single bid."
        )
    narrative = ReportNarrative(
        title="Sealed-bid second-price auction with LLM bidders",
        background=(
            "A sealed-bid second-price auction sells one indivisible item. Each bidder "
            "privately knows only their own valuation, submits exactly one sealed bid "
            "(a finite nonnegative number), and bids are revealed only after every "
            "bidder has committed. The highest bid wins and the winner pays the "
            "second-highest submitted bid. The winner's payoff, also called utility, "
            "equals their own valuation minus the price paid; every other bidder pays "
            "nothing and receives zero. Ties for the highest bid are broken by bidder "
            f"order: {order_text}. There is no reserve price and no budget constraints, "
            "and bidding above or below one's own valuation is allowed. In this run "
            "the private valuations are "
            + ", ".join(f"{aid}: {valuations[aid]:g}" for aid in order)
            + "."
        ),
        rationale=(
            "The experiment asks how private-value LLM bidders behave compared with "
            "truthful bidding. Each bidder is a live language-model policy that sees "
            "only the auction rules and its own valuation before committing one bid. "
            "After the bids are committed, a separately calculated truthful-bidding "
            "reference shows what the same auction would pay under textbook behavior. "
            "Under independent private values with risk-neutral quasi-linear utility, "
            "bidding exactly one's valuation is a weakly dominant strategy, so the "
            "reference is an informative benchmark: comparing recorded bids, winner, "
            "payment and payoffs against it reveals where observed behavior aligns "
            "with or departs from the textbook prediction."
        ),
        interpretation=(
            f"The recorded bids were {bid_lines}. {winner_text} won and paid "
            f"{payment_text}, for payoffs {payoff_lines}. Under the truthful reference "
            f"the payoffs would be {reference_lines}. {match_text} This is a single "
            "run, so it cannot support general claims about how LLM bidders behave; "
            "it only documents what these bidders did under these rules, valuations "
            "and prompts."
        ),
        assumptions=(
            (
                "Independent private values: each bidder knows only their own valuation "
                "for the item (user requirement)."
            ),
            (
                "Risk-neutral quasi-linear utility: the winner's payoff is valuation "
                "minus payment and every other bidder receives zero "
                "(textbook Vickrey convention)."
            ),
            (
                "One indivisible item with no reserve price and no budget constraints "
                "(user requirement)."
            ),
            (
                "Bids are finite nonnegative numbers, and bidding above or below one's "
                "own valuation is legal (user requirement)."
            ),
            (
                f"Highest-bid ties are broken by configuration order: {order_text} "
                "(user convention)."
            ),
            (
                "One simultaneous sealed-bid round with exactly one bid per bidder "
                "(user requirement)."
            ),
        ),
        limitations=(
            (
                "This is a single run with three bidders and one valuation profile, so "
                "it cannot support general claims about LLM bidding behavior."
            ),
            (
                "The observed bids depend on the specific model, prompts and "
                "parameters; other settings may produce different results."
            ),
            (
                "Recorded rationales are the actors' own explanations and do not "
                "independently prove why they bid as they did."
            ),
            (
                "The truthful reference is a separately calculated point comparison, "
                "not a full equilibrium analysis."
            ),
        ),
    )
    return write_experiment_notebook(
        artifact,
        output_directory,
        narrative,
        references=(comparison,),
        figures=(bid_figure, payoff_figure),
    )
