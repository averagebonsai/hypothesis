"""Acceptance tests for the truthful reference and the results notebook.

Reference expectations are hand-derived Vickrey settlements. Notebook tests use
genuine runtime artifacts with distinctive valuations, bids, and rationales, and
assert that every reported number is derived from the saved run.
"""

import json

import pytest
from experiment_extension.auction import SecondPriceAuctionMechanism
from experiment_extension.reference import truthful_second_price
from experiment_extension.report import generate_auction_notebook
from experiment_extension.schemas import BidPayload

from agent_tools.fixtures import fixture_config
from components.library import standard_registry
from simulation_core.execution import JobRunner, LocalBackend
from simulation_core.reports import validate_explanatory_notebook
from simulation_core.request import ExperimentRequest

MECHANISM_ID = "experimental.auction_notebook_141f20fc.second_price"
BID_SCHEMA_ID = "experimental.auction_notebook_141f20fc.bid"
BIDDERS = ("bidder_a", "bidder_b", "bidder_c")


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


def with_rationales(artifact, rationales):
    events = []
    for event in artifact.result.events:
        if event.kind != "committed":
            events.append(event)
            continue
        decisions = tuple(
            decision.model_copy(update={"rationale": rationales[decision.action.actor_id]})
            for decision in event.decisions
        )
        events.append(event.model_copy(update={"decisions": tuple(decisions)}))
    result = artifact.result.model_copy(update={"events": tuple(events)})
    return artifact.model_copy(update={"result": result})


def report_metadata(path):
    return json.loads(path.read_text())["metadata"]["hypothesis_report"]


def test_truthful_reference_matches_hand_derived_values():
    reference = truthful_second_price(
        {"bidder_a": 90.0, "bidder_b": 65.0, "bidder_c": 40.0}, BIDDERS
    )
    assert reference.bids == {"bidder_a": 90.0, "bidder_b": 65.0, "bidder_c": 40.0}
    assert reference.winner == "bidder_a"
    assert reference.payment == 65.0
    assert reference.payoffs == {"bidder_a": 25.0, "bidder_b": 0.0, "bidder_c": 0.0}
    tied = truthful_second_price({"bidder_a": 50.0, "bidder_b": 50.0, "bidder_c": 30.0}, BIDDERS)
    assert tied.winner == "bidder_a"
    assert tied.payment == 50.0
    assert tied.payoffs == {"bidder_a": 0.0, "bidder_b": 0.0, "bidder_c": 0.0}
    upset = truthful_second_price({"bidder_a": 10.0, "bidder_b": 20.0, "bidder_c": 30.0}, BIDDERS)
    assert upset.winner == "bidder_c"
    assert upset.payment == 20.0
    assert upset.payoffs == {"bidder_a": 0.0, "bidder_b": 0.0, "bidder_c": 10.0}


def test_truthful_reference_rejects_bad_inputs():
    with pytest.raises(ValueError):
        truthful_second_price({"bidder_a": 90.0}, BIDDERS)
    with pytest.raises(ValueError):
        truthful_second_price({}, ())
    with pytest.raises(ValueError):
        truthful_second_price({"bidder_a": 90.0}, ("bidder_a",))
    with pytest.raises(ValueError):
        truthful_second_price(
            {"bidder_a": float("nan"), "bidder_b": 65.0, "bidder_c": 40.0}, BIDDERS
        )
    with pytest.raises(ValueError):
        truthful_second_price({"bidder_a": "90", "bidder_b": 65.0, "bidder_c": 40.0}, BIDDERS)


def test_notebook_reports_hand_derived_comparison(tmp_path):
    bids = {"bidder_a": 80.0, "bidder_b": 70.0, "bidder_c": 40.0}
    valuations = {"bidder_a": 90.0, "bidder_b": 65.0, "bidder_c": 40.0}
    artifact = run_scripted_auction(bids, valuations)
    rationales = {
        "bidder_a": "Bidder_a rationale: bid 80 against valuation 90.",
        "bidder_b": "Bidder_b rationale: bid 70 against valuation 65.",
        "bidder_c": "Bidder_c rationale: bid 40 against valuation 40.",
    }
    artifact = with_rationales(artifact, rationales)
    snapshot = artifact.model_dump_json()
    path = generate_auction_notebook(artifact, tmp_path)
    assert path == tmp_path / "results.ipynb"
    content = path.read_text()
    validate_explanatory_notebook(content, artifact)
    assert artifact.model_dump_json() == snapshot
    report = report_metadata(path)
    narrative = report["narrative"]
    assert narrative["title"]
    assert "second-price" in narrative["background"].lower()
    combined = narrative["background"] + narrative["rationale"] + narrative["interpretation"]
    assert "weakly dominant" in combined.lower()
    assert len(narrative["assumptions"]) >= 3
    assert len(narrative["limitations"]) >= 2
    assert len(report["references"]) == 1
    reference = report["references"][0]
    assert "truthful" in reference["name"].lower()
    assert "weakly dominant" in reference["explanation"].lower()
    assert reference["payoffs"] == {"bidder_a": 25.0, "bidder_b": 0.0, "bidder_c": 0.0}
    assert {action["actor_id"]: action["payload"]["bid"] for action in reference["actions"]} == {
        "bidder_a": 90.0,
        "bidder_b": 65.0,
        "bidder_c": 40.0,
    }
    assert reference["source_ticks"] == {}
    assert len(report["figures"]) == 2
    bid_figure = report["figures"][0]
    assert "bid" in bid_figure["title"].lower()
    assert list(bid_figure["categories"]) == ["bidder_a", "bidder_b", "bidder_c"]
    assert bid_figure["series"][0]["label"] == "Bids"
    assert list(bid_figure["series"][0]["values"]) == [80.0, 70.0, 40.0]
    assert bid_figure["series"][1]["label"] == "Valuations"
    assert list(bid_figure["series"][1]["values"]) == [90.0, 65.0, 40.0]
    payoff_figure = report["figures"][1]
    assert "payoff" in payoff_figure["title"].lower()
    assert payoff_figure["series"][0]["label"] == "Actual payoff"
    assert list(payoff_figure["series"][0]["values"]) == [20.0, 0.0, 0.0]
    assert payoff_figure["series"][1]["label"] == "Truthful payoff"
    assert list(payoff_figure["series"][1]["values"]) == [25.0, 0.0, 0.0]
    for rationale in rationales.values():
        assert content.count(rationale) == 0


def test_notebook_derives_from_saved_run(tmp_path):
    bids = {"bidder_a": 55.0, "bidder_b": 55.0, "bidder_c": 30.0}
    valuations = {"bidder_a": 50.0, "bidder_b": 50.0, "bidder_c": 30.0}
    artifact = run_scripted_auction(bids, valuations)
    committed = artifact.result.events[1]
    assert committed.outcome is not None
    assert committed.outcome.metrics["winner"] == "bidder_a"
    assert committed.outcome.metrics["payment"] == 55.0
    assert committed.outcome.payoffs["bidder_a"] == -5.0
    path = generate_auction_notebook(artifact, tmp_path)
    validate_explanatory_notebook(path.read_text(), artifact)
    report = report_metadata(path)
    reference = report["references"][0]
    assert reference["payoffs"] == {"bidder_a": 0.0, "bidder_b": 0.0, "bidder_c": 0.0}
    assert {action["actor_id"]: action["payload"]["bid"] for action in reference["actions"]} == {
        "bidder_a": 50.0,
        "bidder_b": 50.0,
        "bidder_c": 30.0,
    }
    assert list(report["figures"][0]["series"][0]["values"]) == [55.0, 55.0, 30.0]
    assert list(report["figures"][1]["series"][0]["values"]) == [-5.0, 0.0, 0.0]
    assert list(report["figures"][1]["series"][1]["values"]) == [0.0, 0.0, 0.0]


def test_notebook_requires_committed_decisions(tmp_path):
    artifact = run_scripted_auction(
        {"bidder_a": 80.0, "bidder_b": 70.0, "bidder_c": 40.0},
        {"bidder_a": 90.0, "bidder_b": 65.0, "bidder_c": 40.0},
    )
    result = artifact.result.model_copy(
        update={"events": (artifact.result.events[0],), "outcomes": ()}
    )
    truncated = artifact.model_copy(update={"result": result})
    with pytest.raises(ValueError):
        generate_auction_notebook(truncated, tmp_path)
