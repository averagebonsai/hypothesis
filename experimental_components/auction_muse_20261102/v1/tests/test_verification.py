"""Acceptance tests for the settlement check and results notebook generator."""

import json
from pathlib import Path

from auction_fixtures import ACTORS, VALUATIONS, job_result_dict, settle_expected
from experiment_extension.auction import (
    AuctionSettlementCheck,
    generate_results_notebook,
    truthful_reference,
)

from components.library import standard_registry
from simulation_core.execution import JobResult


def test_settlement_check_verifies_valid_artifact() -> None:
    bids = {"bidder_a": 70.0, "bidder_b": 65.0, "bidder_c": 40.0}
    artifact = JobResult.from_json_values(job_result_dict(bids))
    finding = AuctionSettlementCheck().assess(artifact, standard_registry())
    assert finding.status == "verified"
    assert finding.required is True
    winner, payment, payoffs = settle_expected(bids, VALUATIONS, list(ACTORS))
    committed = artifact.result.events[-1]
    assert committed.outcome is not None
    assert committed.outcome.payoffs == payoffs
    assert committed.outcome.metrics["winner"] == winner
    assert committed.outcome.metrics["payment"] == payment
    reference = truthful_reference(dict(VALUATIONS), list(ACTORS))
    assert reference.winner == "bidder_a"
    assert reference.payment == 65.0


def test_settlement_check_fails_tampered_records() -> None:
    bids = {"bidder_a": 70.0, "bidder_b": 65.0, "bidder_c": 40.0}
    registry = standard_registry()
    for tamper in ("payoffs", "winner", "payment", "history"):
        artifact = JobResult.from_json_values(job_result_dict(bids, tamper=tamper))
        finding = AuctionSettlementCheck().assess(artifact, registry)
        assert finding.status == "failed", tamper
    overbid = {"bidder_a": 70.0, "bidder_b": 65.0, "bidder_c": 100.0}
    legal = JobResult.from_json_values(job_result_dict(overbid))
    assert AuctionSettlementCheck().assess(legal, registry).status == "verified"


def test_settlement_check_fails_illegal_or_leaked_records() -> None:
    registry = standard_registry()
    illegal = {"bidder_a": 70.0, "bidder_b": 65.0, "bidder_c": -5.0}
    artifact = JobResult.from_json_values(job_result_dict(illegal))
    assert AuctionSettlementCheck().assess(artifact, registry).status == "failed"
    bids = {"bidder_a": 70.0, "bidder_b": 65.0, "bidder_c": 40.0}
    leaked = JobResult.from_json_values(job_result_dict(bids, leak_actor="bidder_a"))
    assert AuctionSettlementCheck().assess(leaked, registry).status == "failed"
    missing = JobResult.from_json_values(job_result_dict(bids, committed=False))
    assert AuctionSettlementCheck().assess(missing, registry).status == "failed"


def test_notebook_generator_writes_valid_notebook(tmp_path: Path) -> None:
    bids = {"bidder_a": 70.0, "bidder_b": 65.0, "bidder_c": 40.0}
    artifact = JobResult.from_json_values(job_result_dict(bids))
    path = generate_results_notebook(artifact, tmp_path)
    assert path == tmp_path / "results.ipynb"
    notebook = json.loads(path.read_text())
    assert notebook["nbformat"] == 4
    code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
    assert len(code_cells) >= 2
    sources = "\n".join(
        "".join(cell["source"]) if isinstance(cell["source"], list) else cell["source"]
        for cell in notebook["cells"]
    )
    assert "truthful" in sources.lower()
    assert "bidder_a" in sources
    assert "70.0" in sources
    assert "weakly dominant" in sources.lower()
