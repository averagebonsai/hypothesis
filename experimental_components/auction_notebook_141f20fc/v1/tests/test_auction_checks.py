"""Acceptance tests for the auction settlement verification check.

The check independently recomputes the Vickrey settlement from each recorded
committed profile; fixtures are genuine runtime artifacts, with tampered copies
proving that corruption is reported as failed rather than verified.
"""

from experiment_extension.auction import SecondPriceAuctionMechanism
from experiment_extension.checks import AuctionSettlementCheck
from experiment_extension.schemas import BidPayload

from agent_tools.fixtures import fixture_config
from components.library import standard_registry
from simulation_core.execution import JobRunner, LocalBackend
from simulation_core.request import ExperimentRequest

MECHANISM_ID = "experimental.auction_notebook_141f20fc.second_price"
BID_SCHEMA_ID = "experimental.auction_notebook_141f20fc.bid"
BIDDERS = ("bidder_a", "bidder_b", "bidder_c")
VALUATIONS = {"bidder_a": 90.0, "bidder_b": 65.0, "bidder_c": 40.0}
BIDS = {"bidder_a": 80.0, "bidder_b": 70.0, "bidder_c": 40.0}


def config_json(bids, valuations):
    return {
        "world": {
            "actors": [
                {
                    "id": aid,
                    "kind": "bidder",
                    "action_space": {"schemas": {"submit_bid": BID_SCHEMA_ID}},
                    "policy_id": "scripted.v1",
                    "policy_parameters": {"kind": "submit_bid", "payload": {"bid": bids[aid]}},
                }
                for aid in BIDDERS
            ],
            "parameters": {
                "action_kind": "submit_bid",
                "bids_field": "bids",
                "outcome_field": "auction_outcome",
                "tie_break": "configuration_order",
            },
            "initial_public_state": {"rules": "Test auction rules."},
            "initial_private_state": {
                aid: {"facts": {"valuation": valuations[aid]}, "memory": {}} for aid in BIDDERS
            },
        },
        "mechanism_id": MECHANISM_ID,
        "protocol_id": "simultaneous.v1",
        "protocol_parameters": {"rounds": 1},
        "permissions": {
            aid: {
                "public_fields": ["rules"],
                "private_fields": ["valuation"],
                "readable_memory": True,
                "writable_private_fields": [],
                "writable_memory": True,
            }
            for aid in BIDDERS
        },
        "max_steps": 10,
    }


def auction_registry():
    registry = standard_registry()
    registry.mechanisms[MECHANISM_ID] = SecondPriceAuctionMechanism
    registry.action_schemas[BID_SCHEMA_ID] = BidPayload
    return registry


def run_scripted_auction(bids, valuations):
    registry = auction_registry()
    config = fixture_config(config_json(bids, valuations))
    request = ExperimentRequest(hypothesis="Test auction run.", execution_kind="agent_simulation")
    return JobRunner(LocalBackend(registry)).run(request, config)


def replace_committed(artifact, committed):
    events = (artifact.result.events[0], committed)
    outcome = committed.outcome
    assert outcome is not None
    result = artifact.result.model_copy(update={"events": events, "outcomes": (outcome,)})
    return artifact.model_copy(update={"result": result})


def test_settlement_check_verifies_recorded_run():
    artifact = run_scripted_auction(BIDS, VALUATIONS)
    finding = AuctionSettlementCheck().assess(artifact, auction_registry())
    assert finding.status == "verified"
    assert finding.required is True
    assert "bidder_a" in finding.evidence


def test_settlement_check_fails_on_tampered_payment():
    artifact = run_scripted_auction(BIDS, VALUATIONS)
    committed = artifact.result.events[1]
    assert committed.outcome is not None
    tampered_outcome = committed.outcome.model_copy(
        update={"payoffs": {"bidder_a": 999.0, "bidder_b": 0.0, "bidder_c": 0.0}}
    )
    tampered = replace_committed(
        artifact, committed.model_copy(update={"outcome": tampered_outcome})
    )
    finding = AuctionSettlementCheck().assess(tampered, auction_registry())
    assert finding.status == "failed"
    assert "pay" in finding.evidence.lower()


def test_settlement_check_fails_on_tampered_winner():
    artifact = run_scripted_auction(BIDS, VALUATIONS)
    committed = artifact.result.events[1]
    assert committed.outcome is not None
    metrics = dict(committed.outcome.metrics)
    metrics["winner"] = "bidder_c"
    tampered_outcome = committed.outcome.model_copy(update={"metrics": metrics})
    tampered = replace_committed(
        artifact, committed.model_copy(update={"outcome": tampered_outcome})
    )
    finding = AuctionSettlementCheck().assess(tampered, auction_registry())
    assert finding.status == "failed"
    assert "winner" in finding.evidence.lower()


def test_settlement_check_fails_on_illegal_bid():
    artifact = run_scripted_auction(BIDS, VALUATIONS)
    committed = artifact.result.events[1]
    actions = list(committed.actions)
    actions[0] = actions[0].model_copy(update={"payload": {"bid": -5.0}})
    tampered = replace_committed(artifact, committed.model_copy(update={"actions": tuple(actions)}))
    finding = AuctionSettlementCheck().assess(tampered, auction_registry())
    assert finding.status == "failed"
    assert "bid" in finding.evidence.lower()


def test_settlement_check_fails_without_committed_profile():
    artifact = run_scripted_auction(BIDS, VALUATIONS)
    result = artifact.result.model_copy(
        update={"events": (artifact.result.events[0],), "outcomes": ()}
    )
    truncated = artifact.model_copy(update={"result": result})
    finding = AuctionSettlementCheck().assess(truncated, auction_registry())
    assert finding.status == "failed"
