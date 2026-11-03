"""Independent verification of recorded second-price auction settlements."""

from math import isfinite

from pydantic import JsonValue

from agent_tools.checks import VerificationCheck
from agent_tools.specs import VerificationFinding
from simulation_core.execution import JobResult
from simulation_core.registry import ComponentRegistry
from simulation_core.types import Event


def _legal_bid(value: JsonValue, actor_id: str, tick: int) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(  # noqa: TRY004
            f"Illegal recorded bid {value!r} for {actor_id} at tick {tick}: bids must be numbers."
        )
    amount = float(value)
    if not isfinite(amount) or amount < 0:
        raise ValueError(
            f"Illegal recorded bid {value!r} for {actor_id} at tick {tick}: "
            "bids must be finite and nonnegative."
        )
    return amount


def _recorded_valuation(value: JsonValue, actor_id: str, tick: int) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(  # noqa: TRY004
            f"Illegal recorded valuation {value!r} for {actor_id} at tick {tick}: "
            "valuations must be numbers."
        )
    amount = float(value)
    if not isfinite(amount):
        raise ValueError(
            f"Illegal recorded valuation {value!r} for {actor_id} at tick {tick}: "
            "valuations must be finite."
        )
    return amount


def _same_bids(recorded: JsonValue, bids: dict[str, float]) -> bool:
    if not isinstance(recorded, dict) or set(recorded) != set(bids):
        return False
    for aid, expected in bids.items():
        value = recorded[aid]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        if float(value) != expected:
            return False
    return True


class AuctionSettlementCheck(VerificationCheck):
    """Recompute allocation, payment, utilities, ties and bid legality per profile."""

    def assess(self, artifact: JobResult, registry: ComponentRegistry) -> VerificationFinding:
        order = [actor.id for actor in artifact.manifest.simulation.world.actors]
        if len(order) < 2:
            return VerificationFinding(
                id="auction_settlement",
                status="failed",
                evidence="Recorded auction covers fewer than two bidders.",
                required=True,
            )
        raw_kind = artifact.manifest.simulation.world.parameters.get("action_kind")
        expected_kind = raw_kind if isinstance(raw_kind, str) and raw_kind else "submit_bid"
        committed = [event for event in artifact.result.events if event.kind == "committed"]
        if not committed:
            return VerificationFinding(
                id="auction_settlement",
                status="failed",
                evidence="No committed action profile was recorded; nothing to verify.",
                required=True,
            )
        try:
            summaries = [self._verify_event(event, order, expected_kind) for event in committed]
        except ValueError as exc:
            return VerificationFinding(
                id="auction_settlement", status="failed", evidence=str(exc), required=True
            )
        return VerificationFinding(
            id="auction_settlement",
            status="verified",
            evidence="Verified recorded second-price settlement(s): " + "; ".join(summaries),
            required=True,
        )

    @staticmethod
    def _verify_event(event: Event, order: list[str], expected_kind: str) -> str:
        tick = event.state.tick
        if event.outcome is None:
            raise ValueError(f"Committed profile at tick {tick} has no recorded outcome to verify.")
        submitted = [action.actor_id for action in event.actions]
        if len(submitted) != len(order) or set(submitted) != set(order):
            raise ValueError(
                f"Committed bid profile at tick {tick} must contain exactly one bid per bidder."
            )
        bids: dict[str, float] = {}
        for action in event.actions:
            if action.kind != expected_kind:
                raise ValueError(
                    f"Illegal recorded bid kind {action.kind!r} for {action.actor_id} "
                    f"at tick {tick}: expected {expected_kind!r}."
                )
            if set(action.payload) != {"bid"}:
                raise ValueError(
                    f"Illegal recorded bid payload for {action.actor_id} at tick {tick}: "
                    f"{action.payload!r}."
                )
            bids[action.actor_id] = _legal_bid(action.payload["bid"], action.actor_id, tick)
        valuations: dict[str, float] = {}
        for aid in order:
            private = event.state.private.get(aid)
            if private is None or "valuation" not in private.facts:
                raise ValueError(f"Missing recorded valuation for bidder {aid} at tick {tick}.")
            valuations[aid] = _recorded_valuation(private.facts["valuation"], aid, tick)
        winner = max(order, key=lambda aid: bids[aid])
        payment = sorted(bids.values(), reverse=True)[1]
        expected_payoffs = {
            aid: (valuations[aid] - payment if aid == winner else 0.0) for aid in order
        }
        outcome = event.outcome
        if outcome.metrics.get("winner") != winner:
            raise ValueError(
                f"Recorded winner {outcome.metrics.get('winner')!r} disagrees with "
                f"the recomputed winner {winner!r} at tick {tick}."
            )
        recorded_payment = outcome.metrics.get("payment")
        if (
            isinstance(recorded_payment, bool)
            or not isinstance(recorded_payment, (int, float))
            or float(recorded_payment) != payment
        ):
            raise ValueError(
                f"Recorded payment {recorded_payment!r} disagrees with the recomputed "
                f"second-price payment {payment} at tick {tick}."
            )
        recorded_bids = outcome.metrics.get("bids")
        if not _same_bids(recorded_bids, bids):
            raise ValueError(
                f"Recorded bid metrics {recorded_bids!r} disagree with the committed "
                f"bids {bids} at tick {tick}."
            )
        if set(outcome.payoffs) != set(order) or any(
            outcome.payoffs[aid] != expected_payoffs[aid] for aid in order
        ):
            raise ValueError(
                f"Recorded payoffs {outcome.payoffs} disagree with the recomputed "
                f"quasi-linear payoffs {expected_payoffs} at tick {tick}."
            )
        return f"tick {tick}: winner {winner} paid {payment:g} for bids {bids}"
