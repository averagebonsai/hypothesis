"""Opt-in orchestration. Importing/configuring this module starts no model or worker."""

from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from simulation_core.execution import JobManifest
from simulation_core.request import ExperimentRequest

from .authoring import (
    AuthoringBudgetError,
    AuthoringReviewRequired,
    CodingAgent,
    CodingPlan,
    Implementation,
    PlanValidationError,
    materialize,
    private_json,
)
from .bundles import seal_bundle
from .contracts import AuthoringOutcome, ReviewRequest
from .docker_worker import DockerWorker
from .specs import RunReceipt


def _run_authoring(
    agent: CodingAgent,
    request: ExperimentRequest,
    experiment_id: str,
    destination: Path,
    worker: DockerWorker,
    *,
    progress: Callable[[str], None] = print,
) -> AuthoringOutcome:
    """Explicitly opt in to live generation and isolated execution.

    Calls/repairs have no fixed total limit unless the agent was configured with
    max_calls. Scientific plans/tests freeze only after static review succeeds.
    KeyboardInterrupt and transport/worker failures propagate; they are not retried
    forever. Callers decide whether to prepare a worker image before invoking this.
    """
    if destination.exists() or destination.name != experiment_id:
        raise ValueError("Use a fresh experiment directory, never a previous bundle")
    plan: CodingPlan | None = None
    feedback = None
    while True:
        progress(f"Planning call {agent.gateway.calls + 1}: reviewing schema, bindings and tests")
        try:
            plan = agent.plan(request, experiment_id, previous=plan, feedback=feedback)
            break
        except PlanValidationError as exc:
            plan, feedback = exc.plan, str(exc)
        except ValidationError as exc:
            feedback = str(exc)
    private_json(agent.audit / "frozen_plan.json", plan.model_dump(mode="json"))
    previous: Implementation | None = None
    feedback = None
    version = 1
    while True:
        progress(f"Implementation call {agent.gateway.calls + 1}: candidate v{version}")
        try:
            implementation = agent.implement(request, plan, previous=previous, feedback=feedback)
        except (ValidationError, ValueError) as exc:
            if isinstance(exc, (PlanValidationError, AuthoringBudgetError)):
                raise
            feedback = str(exc)
            continue
        candidate = destination / f"v{version}"
        job = materialize(candidate, request, plan, implementation, version)
        seal_bundle(candidate)
        if isinstance(job, JobManifest) and plan.bundle.notebook is not None:
            progress(
                f"Rendering offline problem/theory preview for candidate v{version}; no actor calls"
            )
            preview = worker.render(candidate, job, agent.audit / f"preview-{version}")
            private_json(agent.audit / f"preview-{version}.json", preview.model_dump(mode="json"))
            if not preview.response.passed:
                previous = implementation
                feedback = "Offline preview failed: " + (
                    preview.response.error or "Missing notebook"
                )
                version += 1
                continue
            if agent.content_review:
                review = agent.review_notebook(
                    request,
                    plan,
                    implementation,
                    preview.response.notebook_json or "",
                    observed=False,
                )
                private_json(
                    agent.audit / f"preview-review-{version}.json", review.model_dump(mode="json")
                )
                if not review.approved:
                    previous = implementation
                    feedback = (
                        "Correct these named notebook/content issues before live execution: "
                        + "; ".join(review.issues)
                    )
                    version += 1
                    continue
        progress(f"Validating and running candidate v{version} in the isolated worker")
        receipt = worker.execute(candidate, job, operation="run")
        private_json(agent.audit / f"validation-{version}.json", receipt.model_dump(mode="json"))
        if receipt.response.passed and (
            receipt.response.result is not None or receipt.response.tool_result is not None
        ):
            simulation_candidate = candidate
            report_receipt = None
            report_candidate = None
            report_output = None
            notebook = receipt.response.notebook_json
            if (
                agent.content_review
                and notebook is not None
                and receipt.response.result is not None
            ):
                while True:
                    review = agent.review_notebook(
                        request, plan, implementation, notebook, observed=True
                    )
                    private_json(
                        agent.audit / f"result-review-{version}.json",
                        review.model_dump(mode="json"),
                    )
                    if review.approved:
                        break
                    assert plan.bundle.notebook is not None
                    report_module = (
                        plan.bundle.notebook.generator.split(":")[0].replace(".", "/") + ".py"
                    )
                    revised = agent.implement(
                        request,
                        plan,
                        previous=implementation,
                        feedback="The live run is committed; NEVER rerun it. Modify ONLY "
                        + report_module
                        + ". Preserve every other source byte-for-byte. Repair these editorial issues and return all source files: "
                        + "; ".join(review.issues),
                    )
                    before = {f.path: f.content for f in implementation.files}
                    after = {f.path: f.content for f in revised.files}
                    if set(before) != set(after) or any(
                        before[p] != after[p] for p in before if p != report_module
                    ):
                        return AuthoringOutcome(
                            status="needs_review",
                            receipt=receipt,
                            candidate=str(simulation_candidate),
                            review=ReviewRequest(
                                status="needs_review",
                                reason="Report repair changed scientific source; no live rerun performed",
                                affected_contracts=("report_only",),
                            ),
                        )
                    implementation = revised
                    version += 1
                    report_candidate = destination / f"v{version}"
                    materialize(report_candidate, request, plan, implementation, version)
                    seal_bundle(report_candidate)
                    report_output = agent.audit / f"report-{version}"
                    report_receipt = worker.render(
                        report_candidate, receipt.response.result, report_output
                    )
                    if not report_receipt.response.passed:
                        return AuthoringOutcome(
                            status="needs_review",
                            receipt=receipt,
                            candidate=str(simulation_candidate),
                            review=ReviewRequest(
                                status="needs_review",
                                reason="Report-only validation failed; saved simulation retained",
                                affected_contracts=("report_only",),
                            ),
                        )
                    notebook = report_receipt.response.notebook_json or ""
            progress("Candidate completed with validation and report artifacts")
            return AuthoringOutcome(
                status="completed",
                receipt=receipt,
                candidate=str(simulation_candidate),
                report_receipt=report_receipt,
                report_candidate=None if report_candidate is None else str(report_candidate),
                report_output=None if report_output is None else str(report_output),
            )
        if receipt.response.diagnostic is not None or receipt.actor_api_attempts:
            # Once actors have produced a result, do not silently repeat the experiment
            # to fix its presentation or validation. Preserve it for report-only repair.
            return AuthoringOutcome(
                status="needs_review",
                receipt=receipt,
                candidate=str(candidate),
                review=ReviewRequest(
                    status="needs_review",
                    reason="The primary simulation produced an artifact or attempted live actor calls. Inspect retained evidence; use report-only repair if a saved result exists. Live execution will not be repeated automatically.",
                    affected_contracts=("saved_result", "live_execution"),
                ),
            )
        previous = implementation
        feedback = (
            "\n".join(
                check.name + ":\n" + check.output
                for check in receipt.response.checks
                if not check.passed
            )
            + "\n"
            + (receipt.response.error or "No completed result was returned")
            + "\n"
            + "\n".join(
                finding.id + ": " + finding.evidence
                for finding in receipt.response.verification_findings
                if finding.required and finding.status != "verified"
            )
        )
        version += 1


def run_authoring(
    agent: CodingAgent,
    request: ExperimentRequest,
    experiment_id: str,
    destination: Path,
    worker: DockerWorker,
    *,
    progress: Callable[[str], None] = print,
) -> AuthoringOutcome:
    """Return a structured terminal outcome; no extra model call after needs_review."""
    try:
        return _run_authoring(agent, request, experiment_id, destination, worker, progress=progress)
    except (AuthoringReviewRequired, PlanValidationError) as exc:
        review = (
            exc.review
            if isinstance(exc, AuthoringReviewRequired)
            else ReviewRequest(
                status="needs_review",
                reason=str(exc),
                affected_contracts=("frozen_plan",),
            )
        )
        versions = (
            sorted(destination.glob("v*"), key=lambda path: int(path.name[1:]))
            if destination.exists()
            else []
        )
        validations = sorted(
            agent.audit.glob("validation-*.json"), key=lambda path: int(path.stem.split("-")[-1])
        )
        receipt = (
            RunReceipt.model_validate_json(validations[-1].read_text()) if validations else None
        )
        outcome = AuthoringOutcome(
            status=review.status,
            review=review,
            receipt=receipt,
            candidate=str(versions[-1]) if versions else None,
        )
        private_json(agent.audit / "review_required.json", outcome.model_dump(mode="json"))
        progress("Authoring stopped for " + review.status + ": " + review.reason)
        return outcome
