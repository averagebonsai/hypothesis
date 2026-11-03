"""Acceptance tests for the custom auction verification check."""

from experiment_extension.auction import (
    AuctionParameters,
    BidPayload,
    SecondPriceAuctionMechanism,
)
from experiment_extension.checks import AuctionChecks

from agent_tools.fixtures import fixture_config
from components.library import standard_registry
from simulation_core.execution import JobManifest, JobResult
from simulation_core.request import ExperimentRequest
from simulation_core.runtime import SimulationRuntime

MECHANISM_ID = "experimental.auction_session_bdfb4b4a.second_price_auction"
BID_SCHEMA_ID = "experimental.auction_session_bdfb4b4a.bid_payload"

VALUATIONS = {"bidder_a": 90.0, "bidder_b": 65.0, "bidder_c": 40.0}


def _simulation_dict(bids):
    return {
        "world": {
            "actors": [
                {
                    "id": actor_id,
                    "kind": "bidder",
                    "action_space": {"schemas": {"submit_bid": BID_SCHEMA_ID}},
                    "policy_id": "scripted.v1",
                    "policy_parameters": {
                        "kind": "submit_bid",
                        "payload": {"bid": bid},
                    },
                }
                for actor_id, bid in bids.items()
            ],
            "parameters": {
                "action_kind": "submit_bid",
                "valuation_field": "valuation",
                "rules_field": "auction_rules",
                "history_field": "bid_history",
                "outcome_field": "auction_outcome",
                "value_model": "independent_private_values",
                "utility_model": "quasi_linear",
                "reserve_price": 0.0,
                "budget_constraints": "none",
                "tie_break": "configuration_order",
            },
            "initial_public_state": {"auction_rules": {"format": "sealed_bid_second_price"}},
            "initial_private_state": {
                actor_id: {"facts": {"valuation": value}} for actor_id, value in VALUATIONS.items()
            },
        },
        "mechanism_id": MECHANISM_ID,
        "protocol_id": "simultaneous.v1",
        "protocol_parameters": {"rounds": 1},
        "permissions": {
            actor_id: {
                "public_fields": ["auction_rules"],
                "private_fields": ["valuation"],
            }
            for actor_id in VALUATIONS
        },
        "max_steps": 5,
    }


def _recorded_run(bids):
    registry = standard_registry()
    registry.mechanisms[MECHANISM_ID] = SecondPriceAuctionMechanism
    registry.action_schemas[BID_SCHEMA_ID] = BidPayload
    registry.parameter_schemas[MECHANISM_ID] = AuctionParameters
    config = fixture_config(_simulation_dict(bids))
    result = SimulationRuntime(registry).run(config)
    request = ExperimentRequest(
        hypothesis="Sealed-bid second-price auction offline check.",
        execution_kind="agent_simulation",
    )
    manifest = JobManifest(request=request, simulation=config)
    return JobResult(manifest=manifest, result=result, benchmark=None), registry


def test_custom_check_verified():
    artifact, registry = _recorded_run({"bidder_a": 88.0, "bidder_b": 60.0, "bidder_c": 45.0})
    finding = AuctionChecks().assess(artifact, registry)
    assert finding.id == "auction_rules"
    assert finding.status == "verified"
    assert finding.required is True
    assert finding.evidence != ""


def test_custom_check_detects_tampering():
    artifact, registry = _recorded_run({"bidder_a": 88.0, "bidder_b": 60.0, "bidder_c": 45.0})
    recorded = artifact.result.outcomes[0]
    tampered_payoffs = dict(recorded.payoffs)
    tampered_payoffs["bidder_a"] += 1.0
    tampered_outcome = recorded.model_copy(update={"payoffs": tampered_payoffs})
    events = list(artifact.result.events)
    events[-1] = events[-1].model_copy(update={"outcome": tampered_outcome})
    tampered_result = artifact.result.model_copy(
        update={"outcomes": (tampered_outcome,), "events": tuple(events)}
    )
    tampered = artifact.model_copy(update={"result": tampered_result})
    finding = AuctionChecks().assess(tampered, registry)
    assert finding.id == "auction_rules"
    assert finding.status == "failed"
    assert finding.evidence != ""
