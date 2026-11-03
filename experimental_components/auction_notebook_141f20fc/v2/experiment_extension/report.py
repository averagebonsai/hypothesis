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
            "for any fixed rival bids, no alternative bid can improve the bidder's "
            "payoff. This reference is one theoretically justified strategy profile "
            "for comparison, calculated separately after the recorded bids were "
            "committed; it is not a complete characterization or enumeration of all "
            "equilibria, and a deviation from it does not by itself prove a bid was "
            "irrational."
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
    order_text = ", then ".join(order)
    bidder_count = len(order)

    actions_match = all(bids[aid] == reference.bids[aid] for aid in order)
    raw_payment = outcome.metrics.get("payment")
    payment_value: float | None = None
    if isinstance(raw_payment, (int, float)) and not isinstance(raw_payment, bool):
        payment_value = float(raw_payment)
    payment_match = payment_value is not None and payment_value == reference.payment
    payoffs_match = all(actual_payoffs[aid] == reference.payoffs[aid] for aid in order)
    outcome_match = recorded_winner == reference.winner and payment_match and payoffs_match

    if isinstance(recorded_winner, str) and recorded_winner in order and payment_value is not None:
        winner_valuation = valuations[recorded_winner]
        if payment_value < winner_valuation:
            result_sentence = (
                "The winner gains under this rule because the recorded payment, which "
                "is the second-highest submitted bid, sits below the winner's own "
                "valuation, leaving a positive difference."
            )
        elif payment_value == winner_valuation:
            result_sentence = (
                "The winner breaks even under this rule because the recorded payment, "
                "which is the second-highest submitted bid, equals the winner's own "
                "valuation, leaving no surplus."
            )
        else:
            result_sentence = (
                "The winner loses under this rule because the recorded payment, which "
                "is the second-highest submitted bid, sits above the winner's own "
                "valuation, leaving a negative difference. This is the textbook risk "
                "of bidding above valuation: a higher own bid cannot lower the price "
                "paid, but it can turn a win into a loss."
            )
    else:
        result_sentence = (
            "The recorded winner or payment was not recorded in usable form, so the "
            "gain or loss cannot be interpreted beyond the displayed table."
        )

    if actions_match:
        actions_sentence = "The recorded bids coincide with the truthful reference bids."
    else:
        actions_sentence = (
            "The recorded bids differ from the truthful reference bids for at least one bidder."
        )
    if outcome_match:
        outcome_sentence = (
            "The recorded winner, payment and payoffs coincide with the reference outcome."
        )
    else:
        outcome_sentence = (
            "The recorded winner, payment and payoffs differ from the reference outcome, "
            f"where {reference.winner} would win and pay {reference.payment:g} "
            "(full comparison in the results table)."
        )
    distinction_sentence = (
        "These are two different properties: identical bids guarantee an identical "
        "outcome, but an identical outcome does not imply identical bids. A deviation "
        "from the benchmark on this run does not by itself prove any bid was "
        "irrational, since truthful bidding is only weakly dominant and many motives "
        "can shape a single bid."
    )
    narrative = ReportNarrative(
        title="Sealed-bid second-price auction with LLM bidders",
        background=(
            "A sealed-bid second-price auction sells one indivisible item, an object that "
            f"cannot be split, to {bidder_count} bidders. A valuation is how much the item "
            "is worth to a bidder in money terms: the most they would willingly pay. "
            "Valuations are private and independent: each bidder knows only their own. "
            "A sealed bid is a single number each bidder submits privately, without "
            "seeing any other bid; bids are revealed only after every bidder has "
            "committed. Here each bidder submits exactly one sealed bid, which must be "
            "a finite nonnegative number. The highest bid wins and the winner pays the "
            "second-highest submitted bid, not their own bid. A payoff, also called "
            "utility here, is the bidder's net gain in money terms: the winner's "
            "payoff is their own valuation minus the price paid, while every other "
            "bidder pays nothing and receives zero. This is risk-neutral utility in "
            "simple terms: each bidder cares only about that money difference, not "
            "about risk itself. A reserve is a minimum price the seller requires "
            "before agreeing to sell; here there is no reserve price, so the highest "
            "bid always wins no matter how low. Ties for the highest bid are broken "
            f"by bidder order: {order_text}. Bidding above or below one's own "
            "valuation is allowed."
        ),
        rationale=(
            "The experiment asks how private-value LLM bidders behave compared with "
            "truthful bidding. Each bidder is a live language-model policy that sees "
            "only the auction rules and its own valuation before committing one sealed "
            "bid. After the bids are committed, a separately calculated "
            "truthful-bidding reference shows what the same auction would pay if every "
            "bidder bid exactly their own valuation. Under independent private values "
            "with risk-neutral quasi-linear utility, bidding exactly one's valuation "
            "is a weakly dominant strategy. Weak dominance means that, for any fixed "
            "rival bids, no alternative bid can improve the bidder's payoff: truthful "
            "bidding never does worse and sometimes does better. The logic follows "
            "from the payment rule: because the winner pays the second-highest bid "
            "rather than their own, bidding above valuation cannot lower the price on "
            "a win but risks a price above what the item is worth to the bidder, "
            "while bidding below "
            "valuation cannot lower the price on a win but risks missing a profitable "
            "win. The reference is one theoretically justified strategy profile for "
            "comparison, not a complete characterization or enumeration of all "
            "equilibria; comparing recorded bids, winner, payment and payoffs against "
            "it reveals where observed behavior aligns with or departs from that "
            "textbook benchmark."
        ),
        interpretation=(
            f"{winner_text} won and paid {payment_text} (see the results table and figures "
            "for the full bids and payoffs). Under the second-price rule the winner pays "
            "the second-highest submitted bid rather than their own bid, so the winner's "
            "payoff is their own valuation minus that amount, while every other bidder "
            f"pays nothing and receives zero. {result_sentence} {actions_sentence} "
            f"{outcome_sentence} {distinction_sentence} This is a single run with "
            f"{bidder_count} bidders and one valuation profile, so it cannot support "
            "general claims about how LLM bidders behave; it only documents what these "
            "bidders did under these rules, valuations and prompts."
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
                f"This is a single run with {bidder_count} bidders and one valuation "
                "profile, so it cannot support general claims about LLM bidding behavior."
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
                "The truthful reference is one separately calculated, theoretically "
                "justified strategy profile for comparison, not a complete "
                "characterization or enumeration of all equilibria."
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
