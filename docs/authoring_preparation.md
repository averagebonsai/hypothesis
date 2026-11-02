# Authoring workflow and verification

The previous allocation trials remain retained and unchanged. This guide describes
the current contracts, not the protocol used in those historical trials.

## Roles and execution routes

`CodingAgent.from_environment(project, audit)` selects MODEL_CODING from the host
.env/environment and requests muse-spark-1.3 with max reasoning. It never falls back
to MODEL. `configured_gateway()` and existing live simulation examples continue
using MODEL, normally muse-spark-1.3-contributor. API_KEY remains host-only. Neither
factory makes a model call until explicitly invoked. See Meta's
[reasoning documentation](https://dev.meta.ai/docs/reasoning) for max support.

ExperimentRequest.execution_kind selects tool, agent_simulation, or auto. A tool
plan invokes a namespaced callable without actors, a protocol, a mechanism or a
Nash wrapper. Agent simulations use the established interfaces and keep actor
decisions separate from mathematical references. See [task routing](task_routing.md)
and the proposed input-only second-price auction request. The isolated worker is
still offline: live LLM actors need a credential-isolated broker. Missing actor
access must be reported rather than replaced by scripted decisions.

## Native authoring documents

`agent_tools.contracts.CodingPlan` contains a BundleManifest object, a native
SimulationConfig or ToolInvocation, and SourceFile tests. Embedded JSON strings
for bundle/configuration are rejected; the controller serializes files afterward.
PlanningResponse and ImplementationResponse each carry one document or a
ReviewRequest. A structured needs_review/unsupported outcome terminates the loop
immediately and retains the last receipt/candidate; it does not consume more calls
trying to work around frozen requirements. run_authoring returns AuthoringOutcome.

Coding responses use Meta's non-strict structured-schema surface for open native
maps. The JsonValue schema is represented as unconstrained JSON to remove its
recursive schema definition; Pydantic still validates the complete decoded object,
including fixed fields, finite values and instance-level validators. There is no
JSON-inside-a-string workaround. Actor response handling remains strict. Meta's
[structured-output documentation](https://dev.meta.ai/docs/structured-output)
describes the non-strict surface and its schema limits.

The source allowlist excludes previous bundles, tests, reports, notebooks, .env,
Git history and the controller conversation. Use fresh audit/bundle namespaces;
only the agent's own artifacts and current diagnostics go into repairs. Calls and
responses remain owner-only under ignored _authoring directories. Context and
model/reasoning identities are checked on resume. No fixed total turn/repair cap
is imposed by default; per-call token/payload/timeout and worker limits remain.
The output-token default is configurable and includes the provider reasoning budget.

## Before freezing

The controller applies deterministic Ruff formatting/import ordering before
freezing tests or sealing implementations. It records raw/normalized hashes and
retains the original model response. No expected numerical values, assertions or
scientific rules are changed by this normalization; later validation still applies.

Review checks typed metadata, supplied inputs, component bindings, known capability
mismatches, syntax, actual component use, core strict-tuple fixture construction,
lint and grounded numeric ReferenceCases. Reference cases contain assignments,
expected feasibility and original objective values, checked directly through
ProblemStatement.evaluate. Fixture helpers construct core objects through JSON-aware
boundaries. These checks do not prove arbitrary Python tests correct; contradictions
that remain require a structured review rather than changing production semantics.

Input/output model references derive actual schemas inside the worker. Schemas
for registered Pydantic payload/parameter exports are retained in receipts.
Parent interfaces can be derived from component kind. Reporting/general utilities
need no MethodContract unless declaring mathematical guarantees; solvers still do.

## Behavioral verification

VerificationSpec supports grounded reference_cases, an explicit action_behavior,
parameter_cases and optional custom_checks. No numeric bindings are needed for a
custom-only checker when a domain cannot be expressed by ProblemStatement.

- reject_infeasible selects finite bounds/constraint/shape mutations and declared
  feasible cases. The checker exercises the real schema/protocol/mechanism
  validation path; configuration failures occur outside the rejection assertion.
- unverified makes absence of a rejection claim visible. The library does not
  invent budget, nonnegativity or other economic restrictions.
- custom selects a required VerificationCheck implementation for penalties,
  projection, stochastic or otherwise unsupported behavior. Custom checkers state
  evidence and return verified/failed/unverified/unsupported; they are not
  automatically independent merely because the coding model authored another file.
- parameter_cases clone declared numeric problem/config inputs and instantiate
  fresh mechanisms/views/solvers to test scoring, feasibility and applicable
  benchmark comparisons. They do not call actor policies or claim complete
  stochastic/stateful simulation coverage. Recorded assumptions remain enforced;
  case-specific state/configuration needs a suitable custom checker.

The default numeric checker supports deterministic complete profiles. Other cases
report scope limits. Independent SLSQP supports continuous single-objective problems
and is a numerical cross-check, not a global proof. Framework-owned integration
also checks recorded primary actions and benchmark outputs against the original
problem. Required failed/unverified/unsupported checks prevent acceptance.

## Reports and diagnostics

Agent simulations declare a notebook generator using (JobResult, output_directory)
-> Path. The worker supplies result.json, generates and executes results.ipynb,
then exports the matching approved artifact only after all required checks pass.
Cells read saved results and call external reporting helpers, not actors/models.

Completed artifacts from a failed integration attempt can be retained separately
in receipt.diagnostic and exported under a run-id-unapproved directory with an
UNAPPROVED.json marker. These records can include the executed notebook and
verification findings; they never make receipt.response.passed true. All exports
are owner-only and ignored under experimental_components/_runs. Actual generation,
tests and custom-check imports remain inside the isolated worker, not the host.

## Explicit future execution

```python
from pathlib import Path
from uuid import uuid4
from agent_tools.authoring import CodingAgent
from agent_tools.docker_worker import DockerWorker
from agent_tools.workflow import run_authoring
from simulation_core.request import ExperimentRequest

project = Path.cwd()
request = ExperimentRequest.model_validate_json(
    (project / "experiment_requests/second_price_auction.json").read_text()
)
experiment_id = "auction_" + uuid4().hex[:8]
agent = CodingAgent.from_environment(
    project, project / "experimental_components/_authoring" / experiment_id
)
worker = DockerWorker(project, sandbox="hypothesis-worker")
worker.prepare()
outcome = run_authoring(agent, request, experiment_id,
    project / "experimental_components" / experiment_id, worker)
# Check outcome.status and outcome.review before accessing outcome.receipt.
```

Calling run_authoring is an explicit live-generation/execution action. It has not
been called as part of implementing these changes. The auction's required live
actor broker remains an explicit capability prerequisite.
