"""Reusable sealed-bid second-price auction components.

Highest bid wins and pays the second-highest submitted bid, with highest-bid
ties broken by configuration order and risk-neutral quasi-linear utilities from
private valuations. Bids above or below valuation are legal. All rules are
driven by configuration; no bidder, valuation, winner, or payment is hardcoded.
"""

import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, Field, JsonValue, ValidationError, model_validator

from agent_tools.checks import VerificationCheck
from agent_tools.specs import VerificationFinding
from simulation_core.execution import JobResult
from simulation_core.mechanism import Mechanism
from simulation_core.observation import permissions_for
from simulation_core.registry import ComponentRegistry
from simulation_core.reporting import result_rows
from simulation_core.types import (
    Action,
    FrozenModel,
    ModelCallRecord,
    Outcome,
    SimulationConfig,
    TransitionResult,
    WorldConfig,
    WorldState,
)

TOLERANCE = 1e-9


class BidPayload(FrozenModel):
    """One sealed bid: a finite nonnegative number.

    Strategic quality is never a validity criterion.
    """

    bid: float = Field(ge=0)


class AuctionParameters(FrozenModel):
    """Reusable second-price configuration and textbook conventions."""

    action_kind: str = Field(default="bid", min_length=1)
    valuation_fact: str = Field(default="valuation", min_length=1)
    bids_field: str = Field(default="bids", min_length=1)
    winner_field: str = Field(default="winner", min_length=1)
    payment_field: str = Field(default="payment", min_length=1)
    payoffs_field: str = Field(default="payoffs", min_length=1)
    tie_break_order: tuple[str, ...] = Field(min_length=2)
    pricing: Literal["second_price"] = "second_price"
    values_model: Literal["independent_private_values"] = "independent_private_values"
    utility_model: Literal["risk_neutral_quasilinear"] = "risk_neutral_quasilinear"
    item: Literal["single_indivisible"] = "single_indivisible"
    reserve: float = 0.0
    budgets: Literal["none"] = "none"
    allow_above_valuation: bool = True

    @model_validator(mode="after")
    def references(self) -> Self:
        if any(not actor_id for actor_id in self.tie_break_order):
            raise ValueError("Tie-break order entries must be nonempty")
        if len(set(self.tie_break_order)) != len(self.tie_break_order):
            raise ValueError("Tie-break order entries must be unique")
        if self.reserve != 0.0:
            raise ValueError("This auction requires no reserve price")
        fields = (self.bids_field, self.winner_field, self.payment_field, self.payoffs_field)
        if len(set(fields)) != len(fields):
            raise ValueError("Auction record field names must differ")
        return self


class TruthfulReference(FrozenModel):
    """Post-commitment truthful-bidding reference values."""

    bids: dict[str, float]
    winner: str
    payment: float
    utilities: dict[str, float]


def _as_amount(value: object, *, owner: str, label: str) -> float:
    """Validate one finite nonnegative number without strategic judgment."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} for {owner} must be a number")
    amount = float(value)
    if not math.isfinite(amount):
        raise ValueError(f"{label} for {owner} must be finite")
    if amount < 0:
        raise ValueError(f"{label} for {owner} must be nonnegative")
    return amount


def _close(value: object, expected: float) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isclose(float(value), expected, rel_tol=TOLERANCE, abs_tol=TOLERANCE)
    )


def settle_second_price(
    bids: dict[str, float],
    valuations: dict[str, float],
    order: Sequence[str],
) -> tuple[str, float, dict[str, float]]:
    """First-principles settlement shared by mechanism, reference, and check."""
    ordered = tuple(order)
    winner = ordered[0]
    for actor_id in ordered[1:]:
        if bids[actor_id] > bids[winner]:
            winner = actor_id
    payment = max(bids[actor_id] for actor_id in ordered if actor_id != winner)
    payoffs = {
        actor_id: (valuations[actor_id] - payment if actor_id == winner else 0.0)
        for actor_id in ordered
    }
    return winner, payment, payoffs


def truthful_reference(valuations: dict[str, float], order: Sequence[str]) -> TruthfulReference:
    """Map valuations to truthful bids, winner, payment, and utilities.

    Pure post-commitment reference: bids equal valuations, the highest valuation
    wins with ties broken by ``order``, the payment is the second-highest
    valuation, and the winner earns valuation minus payment. Truthful bidding is
    weakly dominant under these assumptions, not the unique equilibrium.
    """
    ordered = tuple(order)
    if len(ordered) < 2 or len(valuations) < 2:
        raise ValueError("A second-price reference needs at least two bidders")
    if len(ordered) != len(valuations) or set(ordered) != set(valuations):
        raise ValueError("Bidder order must cover exactly the supplied valuations")
    if len(set(ordered)) != len(ordered):
        raise ValueError("Bidder order entries must be unique")
    bids = {
        actor_id: _as_amount(value, owner=actor_id, label="Valuation")
        for actor_id, value in valuations.items()
    }
    winner, payment, utilities = settle_second_price(bids, bids, ordered)
    return TruthfulReference(bids=bids, winner=winner, payment=payment, utilities=utilities)


def _bid_profile(params: AuctionParameters, actions: Sequence[Action]) -> dict[str, float]:
    bids: dict[str, float] = {}
    for action in actions:
        if action.kind != params.action_kind:
            raise ValueError(f"Unexpected action kind from {action.actor_id}")
        try:
            payload = BidPayload.model_validate(action.payload)
        except ValidationError as exc:
            raise ValueError(f"Illegal sealed bid from {action.actor_id}") from exc
        bids[action.actor_id] = payload.bid
    return bids


def _initial_valuations(config: WorldConfig, params: AuctionParameters) -> dict[str, float]:
    valuations: dict[str, float] = {}
    for actor_id in params.tie_break_order:
        private = config.initial_private_state.get(actor_id)
        if private is None or params.valuation_fact not in private.facts:
            raise ValueError(f"Missing private valuation for {actor_id}")
        valuations[actor_id] = _as_amount(
            private.facts[params.valuation_fact], owner=actor_id, label="Valuation"
        )
    return valuations


class SecondPriceMechanism(Mechanism):
    """Reusable second-price settlement with configuration-order tie-breaks."""

    requires_joint_actions = True

    def parameters(self, config: WorldConfig) -> AuctionParameters:
        return AuctionParameters.from_json_values(config.parameters)

    def required_action_schemas(self, config: WorldConfig) -> dict[str, dict[str, type[BaseModel]]]:
        params = self.parameters(config)
        return {actor.id: {params.action_kind: BidPayload} for actor in config.actors}

    def validate_config(self, config: WorldConfig) -> None:
        params = self.parameters(config)
        actor_ids = [actor.id for actor in config.actors]
        if len(params.tie_break_order) != len(actor_ids) or set(params.tie_break_order) != set(
            actor_ids
        ):
            raise ValueError("Tie-break order must cover exactly the configured bidders")
        for actor in config.actors:
            if params.action_kind not in actor.action_space.schemas:
                raise ValueError(f"Bidder {actor.id} must declare the bid action")

    def validate_actions(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> None:
        params = self.parameters(config)
        actor_ids = [actor.id for actor in config.actors]
        seen = [action.actor_id for action in actions]
        if len(actions) != len(actor_ids) or len(set(seen)) != len(seen):
            raise ValueError("Exactly one sealed bid is required per bidder")
        if set(seen) != set(actor_ids):
            raise ValueError("Bid batch must cover exactly the configured bidders")
        _bid_profile(params, actions)

    def evaluate(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> Outcome:
        params = self.parameters(config)
        actor_ids = [actor.id for actor in config.actors]
        if len(actions) != len(actor_ids) or {a.actor_id for a in actions} != set(actor_ids):
            raise ValueError("Evaluation requires a complete joint bid profile")
        bids = _bid_profile(params, actions)
        valuations = _initial_valuations(config, params)
        winner, payment, payoffs = settle_second_price(bids, valuations, params.tie_break_order)
        bids_record: dict[str, JsonValue] = dict(bids)
        metrics: dict[str, JsonValue] = {
            "winner": winner,
            "payment": payment,
            "bids": bids_record,
        }
        return Outcome(payoffs=payoffs, metrics=metrics)

    def transition(
        self, config: WorldConfig, state: WorldState, actions: Sequence[Action]
    ) -> TransitionResult:
        self.validate_actions(config, state, actions)
        params = self.parameters(config)
        outcome = self.evaluate(config, state, actions)
        history = state.public.get(params.bids_field, [])
        if not isinstance(history, list):
            raise TypeError("Bid history must be a list")
        bids_record: dict[str, JsonValue] = dict(_bid_profile(params, actions))
        payoffs_record: dict[str, JsonValue] = dict(outcome.payoffs)
        public: dict[str, JsonValue] = {
            **state.public,
            params.bids_field: [*history, bids_record],
            params.winner_field: outcome.metrics["winner"],
            params.payment_field: outcome.metrics["payment"],
            params.payoffs_field: payoffs_record,
        }
        return TransitionResult(public=public, outcome=outcome)

    def validate_state(self, config: WorldConfig, state: WorldState) -> None:
        params = self.parameters(config)
        history = state.public.get(params.bids_field, [])
        if not isinstance(history, list) or len(history) != state.tick:
            raise ValueError("Bid history must hold one profile per committed tick")
        actor_ids = {actor.id for actor in config.actors}
        for entry in history:
            if not isinstance(entry, dict) or set(entry) != actor_ids:
                raise ValueError("Stored bid profiles must cover exactly the bidders")
            for actor_id, amount in entry.items():
                _as_amount(amount, owner=str(actor_id), label="Stored bid")
        if state.tick == 0:
            return
        for field in (params.winner_field, params.payment_field, params.payoffs_field):
            if field not in state.public:
                raise ValueError("Committed state must record the settlement")
        recorded = history[-1]
        if not isinstance(recorded, dict):
            raise TypeError("Stored bid profiles must cover exactly the bidders")
        bids = {
            str(actor_id): _as_amount(amount, owner=str(actor_id), label="Stored bid")
            for actor_id, amount in recorded.items()
        }
        valuations = _initial_valuations(config, params)
        winner, payment, payoffs = settle_second_price(bids, valuations, params.tie_break_order)
        if state.public[params.winner_field] != winner:
            raise ValueError("Recorded winner disagrees with the bids")
        if not _close(state.public[params.payment_field], payment):
            raise ValueError("Recorded payment disagrees with the bids")
        recorded_payoffs = state.public[params.payoffs_field]
        if not isinstance(recorded_payoffs, dict) or set(recorded_payoffs) != set(payoffs):
            raise ValueError("Recorded payoffs must cover exactly the bidders")
        for actor_id, expected in payoffs.items():
            if not _close(recorded_payoffs[actor_id], expected):
                raise ValueError("Recorded payoffs disagree with the bids")


class AuctionSettlementCheck(VerificationCheck):
    """Independently recompute the settlement and check observation privacy."""

    def assess(self, artifact: JobResult, registry: ComponentRegistry) -> VerificationFinding:
        try:
            evidence = self._verify(artifact)
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            detail = str(exc) or type(exc).__name__
            return VerificationFinding(
                id="auction_settlement",
                status="failed",
                evidence=f"Auction settlement verification failed: {detail}",
                required=True,
            )
        return VerificationFinding(
            id="auction_settlement", status="verified", evidence=evidence, required=True
        )

    def _verify(self, artifact: JobResult) -> str:
        config = artifact.manifest.simulation
        params = AuctionParameters.from_json_values(config.world.parameters)
        committed = [e for e in artifact.result.events if e.kind == "committed"]
        if not committed:
            raise ValueError("no committed bid profile was recorded")
        history = committed[-1].state.public.get(params.bids_field, [])
        if not isinstance(history, list) or len(history) != len(committed):
            raise ValueError("bid history does not match the committed rounds")
        valuations = _initial_valuations(config.world, params)
        winner = ""
        payment = 0.0
        for index, event in enumerate(committed):
            actions = list(event.actions)
            actor_ids = [action.actor_id for action in actions]
            if len(actions) != len(params.tie_break_order) or set(actor_ids) != set(
                params.tie_break_order
            ):
                raise ValueError(f"round {index}: incomplete bid profile")
            bids = _bid_profile(params, actions)
            entry = history[index]
            if (
                not isinstance(entry, dict)
                or {
                    str(aid): _as_amount(v, owner=str(aid), label="Stored bid")
                    for aid, v in entry.items()
                }
                != bids
            ):
                raise ValueError(f"round {index}: bid history disagrees with committed bids")
            winner, payment, payoffs = settle_second_price(bids, valuations, params.tie_break_order)
            outcome = event.outcome
            if outcome is None:
                raise ValueError(f"round {index}: missing outcome")
            if outcome.metrics.get("winner") != winner:
                raise ValueError(f"round {index}: recorded winner disagrees with the bids")
            if not _close(outcome.metrics.get("payment"), payment):
                raise ValueError(f"round {index}: recorded payment disagrees with the bids")
            recorded_bids = outcome.metrics.get("bids")
            if (
                not isinstance(recorded_bids, dict)
                or {
                    str(aid): _as_amount(v, owner=str(aid), label="Recorded bid")
                    for aid, v in recorded_bids.items()
                }
                != bids
            ):
                raise ValueError(f"round {index}: recorded bids disagree with committed bids")
            if set(outcome.payoffs) != set(payoffs) or any(
                not _close(outcome.payoffs[aid], payoffs[aid]) for aid in payoffs
            ):
                raise ValueError(f"round {index}: recorded payoffs disagree with the bids")
            public = event.state.public
            if public.get(params.winner_field) != winner:
                raise ValueError(f"round {index}: recorded winner disagrees with the bids")
            if not _close(public.get(params.payment_field), payment):
                raise ValueError(f"round {index}: recorded payment disagrees with the bids")
            recorded_payoffs = public.get(params.payoffs_field)
            if (
                not isinstance(recorded_payoffs, dict)
                or set(recorded_payoffs) != set(payoffs)
                or any(not _close(recorded_payoffs[aid], payoffs[aid]) for aid in payoffs)
            ):
                raise ValueError(f"round {index}: recorded payoffs disagree with the bids")
        checked = self._verify_privacy(config, list(artifact.result.model_calls))
        return (
            f"Recomputed {len(committed)} committed round(s) from sealed bids and initial "
            f"private valuations (winner {winner}, payment {payment}); bid legality, "
            f"allocation, payment, utilities, tie-breaks, and history all match, and "
            f"{checked} recorded model-call observation(s) expose only each bidder's "
            "own valuation plus the public rules."
        )

    def _verify_privacy(self, config: SimulationConfig, calls: Sequence[ModelCallRecord]) -> int:
        checked = 0
        for call in calls:
            raw = call.request.get("input_json")
            if not isinstance(raw, str):
                raise TypeError(f"model call for {call.actor_id} lacks a recorded input")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"model call for {call.actor_id} has an unreadable input") from exc
            if not isinstance(data, dict) or not isinstance(data.get("observation"), dict):
                raise TypeError(f"model call for {call.actor_id} has an unreadable input")
            observation = data["observation"]
            actor_id = observation.get("actor_id", call.actor_id)
            phase = observation.get("phase", "act")
            if not isinstance(actor_id, str) or not isinstance(phase, str):
                raise TypeError("recorded observation has an invalid identity")
            permissions = permissions_for(config, actor_id, phase)
            public = config.world.initial_public_state
            expected_visible = {
                field: public[field] for field in permissions.public_fields if field in public
            }
            if observation.get("visible") != expected_visible:
                raise ValueError(f"recorded observation for {actor_id} exposes extra public data")
            facts = config.world.initial_private_state.get(actor_id)
            expected_facts: dict[str, JsonValue] = {}
            if facts is not None:
                expected_facts = {
                    field: facts.facts[field]
                    for field in permissions.private_fields
                    if field in facts.facts
                }
            private = observation.get("private", {})
            recorded_facts = private.get("facts", {}) if isinstance(private, dict) else None
            if recorded_facts != expected_facts:
                raise ValueError(
                    f"recorded observation for {actor_id} exposes foreign private data"
                )
            checked += 1
        return checked


def generate_results_notebook(artifact: JobResult, output_directory: Path) -> Path:
    """Write results.ipynb comparing actual bids with the truthful reference.

    Reads only the recorded artifact; notebook cells never call actors or models.
    """
    output_directory.mkdir(parents=True, exist_ok=True)
    rows = result_rows(artifact)
    config = artifact.manifest.simulation
    params = AuctionParameters.from_json_values(config.world.parameters)
    order = list(params.tie_break_order)
    facts = config.world.initial_private_state
    valuations = {
        actor_id: _as_amount(
            facts[actor_id].facts[params.valuation_fact],
            owner=actor_id,
            label="Valuation",
        )
        for actor_id in order
    }
    reference = truthful_reference(dict(valuations), order)
    committed = [event for event in artifact.result.events if event.kind == "committed"]
    last = committed[-1] if committed else None
    actual_bids: dict[str, float] = {}
    actual_winner: str | None = None
    actual_payment: float | None = None
    actual_payoffs: dict[str, float] = {}
    rationales: dict[str, str | None] = {}
    for row in rows["primary_actions"]:
        actor = row["actor"]
        if isinstance(actor, str):
            rationale = row["rationale"]
            rationales[actor] = rationale if isinstance(rationale, str) else None
    if last is not None:
        actual_bids = _bid_profile(params, list(last.actions))
        if last.outcome is not None:
            winner_raw = last.outcome.metrics.get("winner")
            payment_raw = last.outcome.metrics.get("payment")
            actual_winner = winner_raw if isinstance(winner_raw, str) else repr(winner_raw)
            if (
                isinstance(payment_raw, (int, float))
                and not isinstance(payment_raw, bool)
                and math.isfinite(float(payment_raw))
            ):
                actual_payment = float(payment_raw)
            actual_payoffs = dict(last.outcome.payoffs)
    summary = {
        "bidders": order,
        "valuations": valuations,
        "actual_bids": actual_bids,
        "actual_winner": actual_winner,
        "actual_payment": actual_payment,
        "actual_payoffs": actual_payoffs,
        "truthful_bids": reference.bids,
        "truthful_winner": reference.winner,
        "truthful_payment": reference.payment,
        "truthful_utilities": reference.utilities,
        "rationales": rationales,
    }
    embedded = json.dumps(summary, indent=2, sort_keys=True, allow_nan=False)
    assumptions = [a.model_dump(mode="json") for a in artifact.result.assumptions]
    assumptions_json = json.dumps(assumptions, indent=2, allow_nan=False)
    rationale_lines = []
    for actor_id in order:
        text = rationales.get(actor_id) or "(no rationale recorded)"
        rationale_lines.append(f"- **{actor_id}**: {' '.join(str(text).split())}")
    hypothesis = artifact.manifest.request.hypothesis

    cells: list[dict[str, object]] = []

    def add_cell(kind: str, source: str) -> None:
        cell: dict[str, object] = {
            "cell_type": kind,
            "id": f"cell-{len(cells)}",
            "metadata": {},
            "source": source,
        }
        if kind == "code":
            cell.update(execution_count=None, outputs=[])
        cells.append(cell)

    add_cell(
        "markdown",
        "# Sealed-bid second-price auction results\n\n"
        f"{hypothesis}\n\n"
        "This notebook reads the saved job result (`result.json`) recorded during the "
        "run. Rerunning its cells does not call actors or models: bids, rationales, "
        "and payoffs come from the committed record, and the truthful-bidding "
        "reference is recomputed from the recorded private valuations.",
    )
    add_cell(
        "code",
        "from pathlib import Path\n"
        "import json\n"
        "from simulation_core.execution import JobResult\n"
        "from simulation_core.reporting import result_rows\n"
        "\n"
        'artifact = JobResult.model_validate_json(Path("result.json").read_text())\n'
        "rows = result_rows(artifact)\n"
        'print("Run status:", artifact.result.status)\n'
        "\n"
        "params = artifact.manifest.simulation.world.parameters\n"
        'order = list(params["tie_break_order"])\n'
        "initial_private = artifact.manifest.simulation.world.initial_private_state\n"
        'valuations = {aid: initial_private[aid].facts["valuation"] for aid in order}\n'
        "\n"
        'committed = [e for e in artifact.result.events if e.kind == "committed"]\n'
        'print("Committed rounds:", len(committed))\n'
        "if not committed:\n"
        '    print("No committed round was recorded.")\n'
        "    last = None\n"
        "else:\n"
        "    last = committed[-1]\n"
        "    assert last.outcome is not None\n"
        '    bids = {a.actor_id: a.payload["bid"] for a in last.actions}\n'
        '    print("Recorded bids:", json.dumps(bids, indent=2, sort_keys=True))\n'
        '    print("Recorded winner:", last.outcome.metrics["winner"])\n'
        '    print("Recorded payment:", last.outcome.metrics["payment"])\n'
        '    print("Recorded payoffs:", '
        "json.dumps(last.outcome.payoffs, indent=2, sort_keys=True))\n"
        "    # Truthful-bidding reference recomputed from recorded valuations.\n"
        "    truthful_bids = dict(valuations)\n"
        "    truthful_winner = order[0]\n"
        "    for aid in order[1:]:\n"
        "        if truthful_bids[aid] > truthful_bids[truthful_winner]:\n"
        "            truthful_winner = aid\n"
        "    truthful_payment = max(\n"
        "        truthful_bids[aid] for aid in order if aid != truthful_winner\n"
        "    )\n"
        "    truthful_utilities = {\n"
        "        aid: (valuations[aid] - truthful_payment if aid == truthful_winner else 0.0)\n"
        "        for aid in order\n"
        "    }\n"
        '    print("Truthful bids:", json.dumps(truthful_bids, indent=2, sort_keys=True))\n'
        '    print("Truthful winner:", truthful_winner)\n'
        '    print("Truthful payment:", truthful_payment)\n'
        '    print("Truthful utilities:", '
        "json.dumps(truthful_utilities, indent=2, sort_keys=True))\n"
        '    print("Rationales:")\n'
        '    for row in rows["primary_actions"]:\n'
        "        print(f\"- {row['actor']}: {row['rationale']}\")\n",
    )
    add_cell(
        "code",
        "%matplotlib inline\n"
        "import matplotlib.pyplot as plt\n"
        "\n"
        "if not committed:\n"
        '    print("No committed round was recorded; skipping plots.")\n'
        "else:\n"
        "    actors = list(order)\n"
        "    positions = list(range(len(actors)))\n"
        "    fig, axes = plt.subplots(1, 2, figsize=(11, 4))\n"
        "    axes[0].bar(\n"
        "        [x - 0.2 for x in positions],\n"
        "        [float(valuations[a]) for a in actors],\n"
        "        width=0.4,\n"
        '        label="Private valuation",\n'
        "    )\n"
        "    axes[0].bar(\n"
        "        [x + 0.2 for x in positions],\n"
        "        [float(bids[a]) for a in actors],\n"
        "        width=0.4,\n"
        '        label="Actual bid",\n'
        "    )\n"
        "    axes[0].set_xticks(positions, actors)\n"
        '    axes[0].set_ylabel("Amount")\n'
        '    axes[0].set_title("Valuations versus actual bids")\n'
        "    axes[0].legend()\n"
        "    actual_payoffs = last.outcome.payoffs\n"
        "    axes[1].bar(\n"
        "        [x - 0.2 for x in positions],\n"
        "        [float(actual_payoffs[a]) for a in actors],\n"
        "        width=0.4,\n"
        '        label="Actual payoff",\n'
        "    )\n"
        "    axes[1].bar(\n"
        "        [x + 0.2 for x in positions],\n"
        "        [float(truthful_utilities[a]) for a in actors],\n"
        "        width=0.4,\n"
        '        label="Truthful payoff",\n'
        "    )\n"
        "    axes[1].set_xticks(positions, actors)\n"
        '    axes[1].set_ylabel("Payoff")\n'
        '    axes[1].set_title("Actual versus truthful payoffs")\n'
        "    axes[1].legend()\n"
        "    fig.tight_layout()\n"
        "    plt.show()\n",
    )
    add_cell(
        "markdown",
        "## Recorded outcome (embedded at generation time)\n\n"
        "```json\n"
        f"{embedded}\n"
        "```\n\n"
        "### Decision rationales\n\n" + "\n".join(rationale_lines) + "\n\n"
        "### Truthful-bidding reference\n\n"
        "Under independent private values with risk-neutral quasi-linear utility, "
        "bidding one's own valuation is weakly dominant: no bidder can gain by "
        "deviating from its valuation given any fixed bids of the others, because "
        "the winner pays the second-highest bid rather than its own. This reference "
        "was computed after the LLM decisions were committed. It does not claim "
        "truthful bidding is the unique equilibrium, and nontruthful bids are "
        "legal in this auction and are not labeled irrational.\n\n"
        "### Assumptions\n\n"
        "```json\n"
        f"{assumptions_json}\n"
        "```\n\n"
        "Textbook conventions: independent private values (each bidder knows only "
        "its own valuation), risk-neutral quasi-linear utility (the winner earns "
        "valuation minus payment, losers earn zero), one indivisible item, no "
        "reserve price, no budget constraints, and highest-bid ties broken by "
        "bidder configuration order.\n\n"
        "### Limitations\n\n"
        "- One simultaneous sealed-bid round with "
        f"{len(order)} bidders; LLM bidding behavior is stochastic and this run is "
        "a single sample.\n"
        "- The truthful reference is a mathematical comparison computed from "
        "recorded valuations, not a live actor decision.\n"
        "- Sealed bidding was enforced by simultaneous scheduling and per-actor "
        "observation permissions; see the settlement check evidence for privacy "
        "verification.\n",
    )
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}
        },
        "cells": cells,
    }
    path = output_directory / "results.ipynb"
    path.write_text(json.dumps(notebook, indent=2, allow_nan=False) + "\n")
    return path
