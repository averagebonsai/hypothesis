"""Acceptance tests for the auction preview and results notebooks."""

import json
from pathlib import Path

from experiment_extension.auction import (
    AuctionParameters,
    BidPayload,
    SecondPriceAuctionMechanism,
)
from experiment_extension.report import preview, report

from agent_tools.fixtures import fixture_config
from components.library import standard_registry
from simulation_core.execution import JobManifest, JobResult
from simulation_core.reports import SECTIONS, ReportData, result_digest
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
        "max_steps": 5,
    }


def _manifest(bids):
    config = fixture_config(_simulation_dict(bids))
    request = ExperimentRequest(
        hypothesis="Sealed-bid second-price auction offline reporting.",
        execution_kind="agent_simulation",
    )
    return JobManifest(request=request, simulation=config)


def _artifact(bids):
    registry = standard_registry()
    registry.mechanisms[MECHANISM_ID] = SecondPriceAuctionMechanism
    registry.action_schemas[BID_SCHEMA_ID] = BidPayload
    registry.parameter_schemas[MECHANISM_ID] = AuctionParameters
    manifest = _manifest(bids)
    result = SimulationRuntime(registry).run(manifest.simulation)
    return JobResult(manifest=manifest, result=result, benchmark=None)


def test_preview_notebook_pending(tmp_path: Path):
    manifest = _manifest({"bidder_a": 80.0, "bidder_b": 70.0, "bidder_c": 30.0})
    path = preview(manifest, tmp_path)
    assert path.name == "preview.ipynb"
    text = path.read_text()
    assert "Observed results and their interpretation are pending" in text
    assert "65" in text


def test_results_notebook_sections(tmp_path: Path):
    artifact = _artifact({"bidder_a": 88.0, "bidder_b": 60.0, "bidder_c": 45.0})
    path = report(artifact, tmp_path)
    assert path.name == "results.ipynb"
    notebook = json.loads(path.read_text())
    text = "\n".join("".join(cell["source"]) for cell in notebook["cells"])
    for section in SECTIONS:
        assert section in text
    stored = ReportData.model_validate_json(json.dumps(notebook["metadata"]["hypothesis_report"]))
    assert stored.result_sha256 == result_digest(artifact)
    assert len(stored.references) >= 1
    assert "truthful" in stored.references[0].name.lower()
    assert stored.references[0].payoffs["bidder_a"] == 25.0
    assert len(stored.figures) >= 1
    assert set(stored.figures[0].categories) == set(VALUATIONS)
