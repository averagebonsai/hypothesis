"""Worker-side audit of the recorded supply-chain trajectory."""

from experiment_extension.metrics import audit_artifact, daily_records
from experiment_extension.schemas import SupplyChainParameters

from agent_tools.checks import VerificationCheck
from agent_tools.specs import VerificationFinding
from simulation_core.execution import JobResult
from simulation_core.registry import ComponentRegistry


class SupplyChainAuditCheck(VerificationCheck):
    """Recompute conservation, cash-flow, capacity, and timing identities."""

    def assess(self, artifact: JobResult, registry: ComponentRegistry) -> VerificationFinding:
        del registry
        try:
            params = SupplyChainParameters.from_json_values(
                artifact.manifest.simulation.world.parameters
            )
            horizon = params.horizon_days
            committed = [event for event in artifact.result.events if event.kind == "committed"]
            decisions = sum(len(event.decisions) for event in committed)
            if len(committed) != 4 * horizon:
                return VerificationFinding(
                    id="supply_chain_audit",
                    status="failed",
                    evidence=f"Expected {4 * horizon} committed phases, found {len(committed)}",
                )
            if decisions != 5 * horizon:
                return VerificationFinding(
                    id="supply_chain_audit",
                    status="failed",
                    evidence=f"Expected {5 * horizon} decisions, found {decisions}",
                )
            issues = audit_artifact(artifact, artifact.manifest.simulation.world.parameters)
            if issues:
                return VerificationFinding(
                    id="supply_chain_audit",
                    status="failed",
                    evidence="; ".join(issues[:6]),
                )
            records = daily_records(artifact)
            sold = sum(record.sold for record in records)
            lost = sum(record.lost_sales for record in records)
            consolidated = sum(record.consolidated_profit for record in records)
            return VerificationFinding(
                id="supply_chain_audit",
                status="verified",
                evidence=(
                    f"All {horizon} days consistent: component conservation, transfer "
                    f"cancellation, lost-sales accounting, capacity limits, arrival timing, "
                    f"and backlog transitions hold; sold={sold} lost={lost} "
                    f"consolidated={consolidated:g}."
                ),
            )
        except Exception as exc:  # noqa: BLE001 - malformed artifacts fail the finding, never crash the worker
            return VerificationFinding(
                id="supply_chain_audit", status="failed", evidence=f"{type(exc).__name__}: {exc}"
            )
