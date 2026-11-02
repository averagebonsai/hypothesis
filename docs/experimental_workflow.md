# External-agent extension workflow

This toolkit supports an **external coding agent**. The worker validates and runs
submitted bundles. An optional host-side `agent_tools.authoring.CodingAgent` adapter
now makes auditable coding-model calls and records exact prompts and responses; it
does not give the model host filesystem or execution tools. A controller must
orchestrate planning, implementation, validation, and repairs. An external agent
can also use `prompts/external_coding_agent.md` as its task instructions
and follows `prompts/newsimulation.md`, uses the planning schemas,
and submits a bundle to the isolated worker.

## Boundaries and retained files

```text
experimental_components/
  vector_allocation/
    v1/
      bundle.json                 # Gap analysis, extension specs, contracts, tests
      bundle.lock.json            # Exact file inventory and SHA-256 seal
      job.example.json            # Reusable, explicitly illustrative input fixture
      experiment_extension/
        __init__.py
        allocation.py
      tests/
        test_allocation.py
      README.md
  _runs/vector_allocation/v1/
    <run-id>.json                 # Local validation/run receipt and optional result
```

Bundles are outside `src` and never promoted automatically. Version directories
are retained. Once sealed, edits invalidate validation; create a new version.
Receipts bind exact bundle content to an immutable Docker image ID and trusted
framework/dependency digest and operator-selected resource limits. Each run validates the same staged, read-only bytes
it executes. Temporary transport manifests and staging directories are removed;
the versioned source/spec/test bundle and returned audit artifacts remain.
`job.example.json` is a deliberate source fixture, not a leaked temporary manifest.

Receipts can contain private experiment state, are written with owner-only file
permissions, and are ignored by Git by default.
Inspect and export them intentionally. The source bundles are suitable for review;
that does not mean their contents should automatically be published.

The host reads JSON and hashes/copies files. It never imports an experimental
module, runs its tests, or installs its dependencies. Experimental registrations
are applied only to a fresh worker-local registry. Core IDs cannot be replaced.
No runtime or global library edits are needed to use a validated extension.
Framework files are read-only, but experimental Python shares the inner worker
process during execution. This is not an adversarial guarantee that a malicious
extension cannot fabricate results or monkeypatch its own process; host isolation
and mathematical correctness are different properties.

## Planning tools

```sh
uv run python -m agent_tools inventory
uv run python -m agent_tools inspect experimental_components/vector_allocation/v1
```

`agent_tools.specs` provides CapabilityRequirement, CapabilityDecision,
GapAnalysisReport, CustomComponentSpec, AcceptanceTest, and BundleManifest.
Schemas are available through each class's `model_json_schema()`.

Inventory includes existing registry schemas, method contracts, shared primitives,
and curated scalar/finite shape metadata. `compatibility_findings(report)` catches
known scalar/vector mismatches. It is deliberately not a universal capability
reasoner: missing metadata is unknown, and semantic compatibility still needs the
agent's analysis, explicit assumptions, executable preflight, and tests.

Classify missing implementation as EXTEND. Reserve UNSUPPORTED for unresolved
critical information or an interface gap requiring review. Reuse/configuration
and small adapters take precedence over new algorithms. Inputs/outputs are typed
schemas; approved parent interfaces depend on component kind. Pure functions may
use callable contracts. Mathematical extensions reuse MethodContract and its
verified/violated/unverified evidence distinctions.

## Prepare Docker Sandboxes

The first host tooling targets macOS/Linux (POSIX file-descriptor and process
controls); the worker runs Linux/Python 3.13. The installed Docker `sbx` CLI is
supported through its private Docker Engine.
A normal local Docker Engine is also supported by omitting `--sandbox`.

```sh
# First-time machine setup, performed by the user/operator:
sbx login
sbx policy init balanced  # Only if no policy has been initialized; affects sbx globally.

# Create the dedicated mountless shell VM, then build the trusted worker image:
uv run python -m agent_tools --sandbox hypothesis-worker create-sandbox
uv run python -m agent_tools --sandbox hypothesis-worker prepare
```

The VM has no repository workspace mount. Only an explicit copy of `src`, trusted
framework tests, Docker support files, the blind coding prompt, pyproject.toml, and uv.lock is supplied for
image building. `.env`, credentials, Git state, coding-agent settings, and extension
source are excluded. The image uses pinned uv and Python major/minor, locked
packages, and an immutable image ID at execution. Building trusted dependencies
requires network access; experimental execution does not.

`prepare` is an operator action on trusted framework inputs. Changes to those
inputs create a different image tag; execution refuses to use a stale image.
Do not let extension code alter the trusted build inputs or replace this step.

## Seal, validate, and run

```sh
uv run python -m agent_tools seal experimental_components/vector_allocation/v1

uv run python -m agent_tools --sandbox hypothesis-worker validate \
  experimental_components/vector_allocation/v1 \
  --job experimental_components/vector_allocation/v1/job.example.json

uv run python -m agent_tools --sandbox hypothesis-worker run \
  experimental_components/vector_allocation/v1 \
  --job experimental_components/vector_allocation/v1/job.example.json
```

`run` repeats validation before execution. Passing validation never permits host
execution. The inner container is nonroot with read-only framework and bundle,
no network, no Docker socket, no API credentials, no extra Linux capabilities,
no privilege escalation, limited CPU/memory/process count, bounded output, and a
host-enforced wall-clock deadline. Only scratch `/tmp` is writable. Containers are
removed on success/failure; timeout/output-limit paths also attempt forced cleanup.
No shell interpolation is used for command arguments. Defaults are 180 seconds,
2 GiB memory with swap disabled, 2 CPUs, 128 processes, and 4 MB combined
command output. The host-side WorkerLimits contract allows bounded operator
configuration; untrusted bundle metadata cannot add Docker permissions.

Validation runs Ruff, mypy, bundle acceptance tests plus framework-maintained
integration checks, and existing regressions. Declared acceptance tests must
actually execute; a receipt cannot report success with missing stages. The worker
builds a fresh namespaced registry and performs the normal compatibility preflight.
Successful `run` returns the existing JobResult with primary decisions, benchmarks,
method applicability, event snapshots, and provenance.

This first worker is intentionally offline: live LLM policies are not injected.
A future credential-isolated model broker is separate work. Do not pass `.env` or
API keys to an experimental container to bypass this restriction. An external
coding agent may have its own separately configured model access; the component
validation/run worker does not inherit it.

Docker isolation protects the host boundary; tests are not a proof that arbitrary
code is benign or that an arbitrary mathematical claim is true. An experiment's
own tests can be wrong. The immutable framework checks, independent references,
manual review, and absence of automatic global promotion remain important.

## First unfamiliar trial

The retained vector-allocation bundle was authored by the interactive coding
assistant as an infrastructure trial, without calling a separate model. It
uses the existing trusted runtime, scripted policy, simultaneous protocol, game
view adapter, and benchmark runner. New code adds a vector payload, coupled
simplex feasibility, quadratic scoring, an analytical projection, and a one-actor
optimal-response adapter. It does not edit simulation_core or standard_registry.

For budget 10 and target (8,6), the scripted primary action (5,5) scores -10. The
separate optimum (6,4) scores -8, giving a possible improvement of 2. The benchmark
is a single-actor Nash optimum, equivalent here to own-objective optimization.
These are illustrative deterministic fixtures, not live-model observations.

Acceptance checks include closed-form boundary cases, an independently reduced
one-dimensional feasible grid, invalid inputs, integration and primary-action
preservation, and actual container restrictions. The full bundle is never imported
on the host. Do not run `pytest experimental_components/...` locally.

When validation fails, keep the receipt, classify the failure, and repair only the
implementation when intent is clear. Record repair_counts per stable failure ID.
During the diagnostic phase there is no fixed coding-turn or repair-count cap;
an operator may explicitly configure one. The optional run_authoring controller
records successive implementation versions and counts. Publish changes under a
new version. Scientific assumptions,
objectives, constraints, required tests, or thresholds need explicit review to
change. New dependencies require approval, a locked update, and a new trusted image.

## Blind live coding-model trial

The optional adapter loads `prompts/blind_coding_agent.md` into the request's
instructions field. This is the active, experiment-independent API prompt;
`prompts/external_coding_agent.md` is the general SOP for a separately operated
agent with development tools. Experiment-specific definitions belong in the
request and resolved configuration, not either prompt.
It sends an explicit allowlist of toolkit source interfaces,
the inventory, and a fresh `ExperimentRequest`. It excludes prior bundles,
results, tests, notebooks, documentation, credentials, Git history, and the
interactive conversation. Repairs receive only the model's own artifacts and
validation diagnostics. The model has no filesystem tools. Credentials stay in
the host transport; the execution worker remains offline.

Each audit records source and prompt hashes, exact requests/responses, usage, and
provider IDs, with owner-only permissions under ignored `_authoring` directories.
The adapter limits per-call output tokens and payload sizes. Coding calls are
uncapped by default; max_calls can explicitly impose a limit. Resume checks the same
context and retains consumed call counts. API generation and Docker execution are
separate operations; API success is not validation success.

See [structured problems](problem_statements.md) and the
[actual live trial report](../experimental_components/allocation_trial/TRIAL.md).
The first live submission failed validation. Its passing self-tests did not test
its actual components, reinforcing the need for framework-owned integration and
independent verification. No held-out evaluation was run after that failure.

The [next-trial preparation guide](authoring_preparation.md) describes the new
pre-freeze plan/test checks, independent structured-problem verification, notebook
generator/execution/export contract, reduced context and uncapped diagnostic
workflow. The later allocation_live_8f8bf161 report records the live diagnostic
trial. Current native contracts/model roles/routing have offline checks; the
new auction request has not been run. Read the preparation guide for the current
API: CodingPlan uses native objects, run_authoring returns AuthoringOutcome,
and a review request terminates the controller instead of extending the repair loop.
