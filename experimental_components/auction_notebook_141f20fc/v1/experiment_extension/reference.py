"""Post-commit truthful-bidding point reference (not an equilibrium solver)."""

from collections.abc import Sequence
from math import isfinite

from simulation_core.types import FrozenModel


class TruthfulReference(FrozenModel):
    """Bids equal to valuations with the resulting Vickrey winner and payoffs."""

    bids: dict[str, float]
    winner: str
    payment: float
    payoffs: dict[str, float]


def truthful_second_price(
    valuations: dict[str, float], actor_order: Sequence[str]
) -> TruthfulReference:
    """Settle the auction as if every bidder bid exactly their private valuation."""
    order = list(actor_order)
    if len(order) < 2 or len(set(order)) != len(order):
        raise ValueError("Truthful reference requires at least two distinct bidders")
    if set(valuations) != set(order):
        raise ValueError("Valuations must cover exactly the configured bidders")
    bids: dict[str, float] = {}
    for aid in order:
        value = valuations[aid]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Valuation for {aid} must be a number")  # noqa: TRY004
        amount = float(value)
        if not isfinite(amount):
            raise ValueError(f"Valuation for {aid} must be finite")
        bids[aid] = amount
    winner = max(order, key=lambda aid: bids[aid])
    payment = sorted(bids.values(), reverse=True)[1]
    payoffs = {aid: (bids[aid] - payment if aid == winner else 0.0) for aid in order}
    return TruthfulReference(bids=bids, winner=winner, payment=payment, payoffs=payoffs)
