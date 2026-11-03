"""Offline integration: full runs, audits, recovery branches, notebooks."""

import json

from experiment_extension.bounds import physical_bounds
from experiment_extension.checks import SupplyChainAuditCheck
from experiment_extension.mechanism import SupplyChainMechanism
from experiment_extension.metrics import (
    audit_artifact,
    daily_records,
    recovery_report,
    restoration_day,
)
from experiment_extension.report import preview, report
from experiment_extension.schemas import SupplyChainParameters
from helpers import draft_manifest, experiment_registry, run_offline, settle_metrics

from simulation_core.execution import JobResult
from simulation_core.reports import validate_explanatory_notebook, validate_preview_notebook


def _check_composition(artifact: JobResult) -> None:
    mechanism = SupplyChainMechanism()
    assert mechanism.validate_config(artifact.manifest.simulation.world) is None
    assert artifact.manifest.simulation.protocol_id == "sequential.v1"


def test_preview_leaves_results_pending(tmp_path) -> None:
    manifest = draft_manifest()
    _check_composition(JobResult(manifest=manifest, result=run_offline("baseline").result))
    path = preview(manifest, tmp_path / "preview")
    assert path.name == "preview.ipynb"
    content = path.read_text()
    validate_preview_notebook(content)
    assert "Observed results and their interpretation are pending" in content
    assert "710" in content  # calculated physical bound
    assert "Pending live execution" in content


def test_baseline_run_reports_nine_days() -> None:
    artifact = run_offline("baseline")
    _check_composition(artifact)
    assert artifact.result.status == "completed"
    assert len(artifact.result.outcomes) == 36
    decisions = sum(len(event.decisions) for event in artifact.result.events)
    assert decisions == 45
    records = daily_records(artifact)
    assert [record.day for record in records] == list(range(1, 10))
    assert sum(record.sold for record in records) == 630
    assert sum(record.lost_sales for record in records) == 90
    assert settle_metrics(artifact, 5)["lost_sales"] == 10
    assert settle_metrics(artifact, 6)["lost_sales"] == 40
    assert settle_metrics(artifact, 7)["lost_sales"] == 40
    assert audit_artifact(artifact, artifact.manifest.simulation.world.parameters) == ()
    params = SupplyChainParameters.from_json_values(artifact.manifest.simulation.world.parameters)
    recovery = recovery_report(
        [record.lost_sales for record in records], restoration_day(params), params.horizon_days
    )
    assert restoration_day(params) == 7
    assert recovery.observed is False
    assert recovery.streak_start is None


def test_hoard_run_observes_recovery_streak() -> None:
    artifact = run_offline("hoard")
    _check_composition(artifact)
    records = daily_records(artifact)
    assert sum(record.sold for record in records) == 240
    assert sum(record.lost_sales for record in records) == 480
    assert audit_artifact(artifact, artifact.manifest.simulation.world.parameters) == ()
    params = SupplyChainParameters.from_json_values(artifact.manifest.simulation.world.parameters)
    recovery = recovery_report(
        [record.lost_sales for record in records], restoration_day(params), params.horizon_days
    )
    assert recovery.observed is True
    assert recovery.streak_start == 7
    assert recovery.confirmation_day == 9
    assert recovery.lag_days == 0


def test_final_report_structure_and_content(tmp_path) -> None:
    artifact = run_offline("baseline")
    _check_composition(artifact)
    path = report(artifact, tmp_path / "report")
    assert path.name == "results.ipynb"
    content = path.read_text()
    validate_explanatory_notebook(content, artifact)
    notebook = json.loads(content)
    figures = notebook["metadata"]["hypothesis_report"]["figures"]
    assert len(figures) == 6
    markdown = "\n".join(
        "".join(cell["source"]) if isinstance(cell["source"], list) else cell["source"]
        for cell in notebook["cells"]
        if cell["cell_type"] == "markdown"
    )
    assert "not observed within the horizon" in markdown
    assert "630" in markdown
    assert "Deterministic offline test plan" not in markdown
    assert "/world/" not in markdown
    assert "```json" not in markdown.lower()
    assert physical_bounds(artifact.manifest.simulation.world.parameters).overall_sales_bound == 710


def test_hoard_report_marks_recovery_observed(tmp_path) -> None:
    artifact = run_offline("hoard")
    _check_composition(artifact)
    content = report(artifact, tmp_path / "report").read_text()
    validate_explanatory_notebook(content, artifact)
    assert "confirmed on day 9" in content
    assert "240" in content


def test_audit_catches_tampered_result() -> None:
    artifact = run_offline("baseline")
    _check_composition(artifact)
    registry = experiment_registry()
    assert SupplyChainAuditCheck().assess(artifact, registry).status == "verified"
    events = []
    tampered = False
    for event in artifact.result.events:
        if (
            not tampered
            and event.actions
            and event.actions[0].kind == "produce"
            and event.outcome is not None
            and event.outcome.metrics.get("day") == 1
        ):
            metrics = dict(event.outcome.metrics)
            metrics["manufacturer_profit"] = float(metrics["manufacturer_profit"]) + 1.0
            payoffs = dict(event.outcome.payoffs)
            payoffs["manufacturer"] = float(payoffs["manufacturer"]) + 1.0
            outcome = event.outcome.model_copy(update={"metrics": metrics, "payoffs": payoffs})
            events.append(event.model_copy(update={"outcome": outcome}))
            tampered = True
        else:
            events.append(event)
    assert tampered
    broken = artifact.model_copy(
        update={"result": artifact.result.model_copy(update={"events": tuple(events)})}
    )
    issues = audit_artifact(broken, broken.manifest.simulation.world.parameters)
    assert issues
    finding = SupplyChainAuditCheck().assess(broken, registry)
    assert finding.status == "failed"


def test_composition_reuses_trusted_core() -> None:
    from experiment_extension.policy import SupplyChainPolicy

    from components.policies.llm import LLMPolicy
    from simulation_core.mechanism import Mechanism

    artifact = run_offline("baseline")
    _check_composition(artifact)
    assert issubclass(SupplyChainMechanism, Mechanism)
    assert issubclass(SupplyChainPolicy, LLMPolicy)
    assert artifact.manifest.simulation.protocol_id == "sequential.v1"
    assert artifact.manifest.simulation.mechanism_id.endswith(".mechanism.supplychainmechanism.v1")


def test_no_live_actor_calls_offline() -> None:
    for scenario in ("baseline", "hoard"):
        artifact = run_offline(scenario)
        _check_composition(artifact)
        assert artifact.result.model_calls == ()
        for event in artifact.result.events:
            assert event.model_calls == ()
            for decision in event.decisions:
                assert decision.rationale
