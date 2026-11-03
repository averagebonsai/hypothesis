"""Independent verification of the recorded second-price auction run."""

from math import isclose, isfinite

from experiment_extension.auction import AuctionParameters, BidPayload

from agent_tools.checks import VerificationCheck
from agent_tools.specs import VerificationFinding
from simulation_core.execution import JobResult
from simulation_core.registry import ComponentRegistry


def _clear(bids: dict[str, float], order: tuple[str, ...]) -> tuple[str, float]:
    # Separate clearing implementation so the check does not reuse the mechanism.
    winner = min(order, key=lambda actor: (-bids[actor], order.index(actor)))
    payment = sorted(bids.values(), reverse=True)[1]
    return winner, payment


class AuctionChecks(VerificationCheck):
    def assess(self, artifact: JobResult, registry: ComponentRegistry) -> VerificationFinding:
        del registry
        try:
            return self._assess(artifact)
        except ValueError as exc:
            return VerificationFinding(
                id="auction_rules", status="failed", evidence=str(exc), required=True
            )

    def _assess(self, artifact: JobResult) -> VerificationFinding:
        config = artifact.manifest.simulation
        params = AuctionParameters.model_validate(config.world.parameters)
        order = tuple(actor.id for actor in config.world.actors)
        committed = [e for e in artifact.result.events if e.kind == "committed"]
        if not committed:
            return VerificationFinding(
                id="auction_rules",
                status="unverified",
                evidence="No committed rounds recorded; nothing to verify.",
                required=True,
            )
        summaries: list[str] = []
        for event in committed:
            bids: dict[str, float] = {}
            for action in event.actions:
                if action.kind != params.action_kind:
                    raise ValueError(f"Unexpected action kind: {action.kind}")
                if action.actor_id in bids:
                    raise ValueError(f"Duplicate action for {action.actor_id}")
                bids[action.actor_id] = BidPayload.model_validate(action.payload).bid
            if set(bids) != set(order):
                raise ValueError("Committed actions do not cover every bidder")
            valuations: dict[str, float] = {}
            for actor_id in order:
                if actor_id not in event.state.private:
                    raise ValueError(f"Missing private state for {actor_id}")
                value = event.state.private[actor_id].facts.get(params.valuation_field)
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not isfinite(value)
                    or value < 0
                ):
                    raise ValueError(f"Invalid valuation for {actor_id}")
                valuations[actor_id] = float(value)
            winner, payment = _clear(bids, order)
            expected = {
                actor_id: (valuations[actor_id] - payment if actor_id == winner else 0.0)
                for actor_id in order
            }
            recorded = event.outcome
            if recorded is None:
                raise ValueError("Committed round lacks a recorded outcome")
            if set(recorded.payoffs) != set(order):
                raise ValueError("Recorded payoffs do not cover every bidder")
            for actor_id in order:
                if not isclose(
                    recorded.payoffs[actor_id],
                    expected[actor_id],
                    rel_tol=1e-9,
                    abs_tol=1e-9,
                ):
                    raise ValueError(
                        f"Payoff mismatch for {actor_id}: recorded "
                        f"{recorded.payoffs[actor_id]}, expected {expected[actor_id]}"
                    )
            recorded_winner = recorded.metrics.get("winner")
            recorded_payment = recorded.metrics.get("payment")
            if recorded_winner != winner:
                raise ValueError(f"Winner mismatch: recorded {recorded_winner}, expected {winner}")
            if (
                isinstance(recorded_payment, bool)
                or not isinstance(recorded_payment, (int, float))
                or not isclose(recorded_payment, payment, rel_tol=1e-9, abs_tol=1e-9)
            ):
                raise ValueError(
                    f"Payment mismatch: recorded {recorded_payment}, expected {payment}"
                )
            summaries.append(
                f"round at tick {event.state.tick}: winner {winner}, "
                f"payment {payment}, payoffs {expected}"
            )
        final = artifact.result.final_state
        history = final.public.get(params.history_field, [])
        if not isinstance(history, list) or len(history) != len(committed):
            raise ValueError("Recorded bid history does not match committed rounds")
        for event, batch in zip(committed, history, strict=True):
            expected_batch = {
                action.actor_id: BidPayload.model_validate(action.payload).bid
                for action in event.actions
            }
            if batch != expected_batch:
                raise ValueError("Recorded bid history differs from committed bids")
        return VerificationFinding(
            id="auction_rules",
            status="verified",
            evidence="; ".join(summaries)
            + ". All bids finite and nonnegative, configuration-order tie-break "
            "applied, and recorded history is consistent.",
            required=True,
        )
