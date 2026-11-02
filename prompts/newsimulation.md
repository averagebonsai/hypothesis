# Standard Operating Procedure: Developing New Simulation Components

## Objective

Enable the coding agent to implement missing simulation capabilities while preserving the integrity, reusability, and correctness of the existing simulation framework.

New functionality should be introduced through approved extension interfaces wherever possible, rather than modifying the trusted runtime or existing framework contracts.

This SOP is for an external coding agent, not an autonomous code-generation controller. Use the data-only tools in `agent_tools`; source imports, tests, and experimental execution happen only inside the Docker worker. See `docs/experimental_workflow.md` for commands and the retained bundle format.

## Step 1 — Identify the missing capability

Before writing code:

1. Decompose the requested experiment into actors, action spaces, policies, mechanisms, protocols, solvers, state requirements, and outcome metrics.
2. Search the component registry for existing implementations.
3. Classify each requirement as `REUSE`, `COMPOSE`, `EXTEND`, or `UNSUPPORTED`.
   - Use EXTEND for a missing implementation that fits an approved interface.
   - Use UNSUPPORTED for simulation-critical missing information or an interface gap; record the reason and request review.
4. Identify the smallest missing capability that prevents implementation.
5. Do not generate a new domain implementation if configuration or existing adapters suffice. Small composition adapters are allowed when required.

If the requirement cannot be expressed through existing interfaces, flag it for architectural review.

Additionally, this analysis should also assess compatibility amongst existing tools, not just component availability. It should compare requirements such as but not limited to:
- Scalar versus vector decisions, including dimension per actor.
- Interval bounds versus coupled constraints.
- Continuous versus discrete actions.
- Deterministic versus stochastic evaluation.
- Timing, information access, and state requirements.
- Required guarantees and the evidence supporting their preconditions.

## Step 2 — Produce a typed extension specification

For each required extension, generate a `CustomComponentSpec` containing:

- Name and component type.
- Purpose.
- Parent interface, if applicable.
- Typed input and output JSON schemas.
- Implementation details.
- Dependencies on existing tools.
- Integration requirements.
- Mathematical or behavioral assumptions as existing MethodContract requirements and evidence.
- Required software and mathematical tests.
- Description of the capability gap being addressed.

The specification must be completed before implementation begins. Use BundleManifest and CustomComponentSpec, with approved parent identifiers, namespaced exports, explicit dependencies, declared acceptance cases and their independent reference, and the capability gap addressed. Classify scalar/vector shape and constraints per actor, not merely the aggregate solver array shape. Registry inventory also lists shared tools; missing metadata means unknown compatibility.

## Step 3 — Define acceptance tests

Generate tests before implementing the extension.

Tests must cover:

1. **Interface correctness:** Inputs, outputs, types, and parent-class contracts.
2. **Functional correctness:** Expected outputs for known inputs.
3. **Mathematical correctness:** Analytical benchmarks, invariants, (known) boundary conditions, or limiting cases where applicable.
4. **Integration correctness:** Compatibility with the existing runtime and components.
5. **Failure behavior:** Invalid inputs, infeasible conditions, numerical errors, and resource limits.

For instance, declare convexity as a required precondition when the method needs it (say, there's a new solver being implemented). Establish it using suitable mathematical evidence. Reject execution when that requirement is violated or remains unverified. Positive sampled checks do not establish global convexity.

Reuse framework-maintained contract tests and independently verified benchmarks wherever available.

Do not weaken, delete, or rewrite required tests to make an implementation pass. Framework-maintained checks are outside the bundle and cannot be replaced. A demonstrably incorrect specification or test needs an explicit reviewed revision, with the reason retained. Numerical agreement with a test derived from the same mistaken formula is not independent validation.

## Step 4 — Implement the extension

Implement the smallest component that satisfies the specification.

Requirements:

- Inherit the appropriate approved parent interface for framework components. Equilibrium solvers implement `_solve` under the existing checked `solve` template; pure mathematical functions may use callable contracts.
- Reuse existing registered utilities and algorithms.
- Do not duplicate existing numerical solvers or state-management functionality.
- Do not modify the trusted runtime, core interfaces, or validation rules.
- Keep new functionality isolated in its own module.
- Preserve type safety and explicit input/output contracts.
- Do not introduce new dependencies without approval.

If implementation requires changes to trusted interfaces or architectural assumptions, stop and request review.

## Step 5 — Execute validation

Run all applicable tests in an isolated execution environment.

Use `uv` for dependency management and the project's locked dependency versions. Build trusted dependencies before loading extensions; no dependency installation or network access occurs during experimental validation/execution. Use a mountless Docker sbx shell VM and its private Docker Engine, or an operator-managed Docker Engine. The restricted inner container is nonroot, read-only outside scratch space, network-disabled, capability-restricted, and has CPU/memory/PID/output/time limits. Do not mount repository secrets, coding-agent settings, the host Docker socket, or `.env`. Passing tests never permits host imports or execution.

Validate:

- Interface compliance.
- Unit tests.
- Mathematical benchmarks.
- Integration tests.
- Existing regression tests.
- Static analysis and type checks.
- Resource limits and execution restrictions.

Record test outcomes, failures, and diagnostics. Seal the bundle before validation, staging the exact hashed bytes read-only. Receipts bind source/spec/tests to the resolved image and framework/dependency digest. The CLI validates all required stages and retains receipts outside the sealed version. The source bundle and example fixtures persist; per-run transport files are temporary.

## Step 6 — Diagnose and repair

If validation fails:

1. Classify the failure as an implementation defect, numerical limitation, specification problem, or architectural incompatibility.
2. Automatically repair implementation defects when the intended behavior is unambiguous.
3. Rerun all relevant tests after each repair.
4. Limit automatic repair attempts to 2 attempts (totally 3 attempts at constructing a solution) per stable failure identified. Record repair_counts and keep every attempted version and validation receipt. Do not reset failure IDs to evade the limit.
5. Never silently change the experiment's scientific assumptions, objective functions, constraints, or acceptance thresholds.

Escalate unresolved failures for human review.

## Step 7 — Register the extension

After passing validation, use the extension only in an isolated experimental run through a fresh job-local registry overlay. Keep it under `experimental_components/<experiment_id>/<version>/`, outside `src`, with bundle.json, source, acceptance tests, README, and bundle.lock.json. Use `experiment_extension` as the import namespace; the host treats its files only as data. Existing approved IDs cannot be overwritten. Changes after sealing require a new version and validation; keep older versions for inspection.

Use the validated byte snapshot for execution, retaining the matching receipt and result. Do not add experimental imports to components.library or the global registry. The offline trial uses scripted actors; live model access requires a separate credential-isolated design.

(Not implemented now) In future iterations, we will develop a process that allows for newly developed extensions to enter the global, reusable component registry. It would require a review of:
- Interface compliance.
- Test adequacy.
- Mathematical and behavioral assumptions.
- Compatibility with existing components.
- Scope of supported use cases.
- Security and dependency requirements.

## Non-negotiable rules

- Prefer reuse over new implementation.
- Never silently modify trusted framework code.
- Never invent missing scientific assumptions without disclosure.
- Never treat numerical convergence alone as proof of mathematical correctness.
- Never execute untrusted generated code directly in the host controller. They should remain in an isolated worker during testing and experimental execution.

The objective is to expand the toolkit through small, tested, reusable capabilities — not to create a separate bespoke simulation engine for every new experiment.
