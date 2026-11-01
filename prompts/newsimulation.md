# Standard Operating Procedure: Developing New Simulation Components

## Objective

Enable the coding agent to implement missing simulation capabilities while preserving the integrity, reusability, and correctness of the existing simulation framework.

New functionality should be introduced through approved extension interfaces wherever possible, rather than modifying the trusted runtime or existing framework contracts.

## Step 1 — Identify the missing capability

Before writing code:

1. Decompose the requested experiment into actors, action spaces, policies, mechanisms, protocols, solvers, state requirements, and outcome metrics.
2. Search the component registry for existing implementations.
3. Classify each requirement as `REUSE`, `COMPOSE`, `EXTEND`, or `UNSUPPORTED`.
4. Identify the smallest missing capability that prevents implementation.
5. Do not generate new code if existing components can satisfy the requirement.

If the requirement cannot be expressed through existing interfaces, flag it for architectural review.

## Step 2 — Produce a typed extension specification

For each required extension, generate a `CustomComponentSpec` containing:

- Name and component type.
- Purpose and expected behavior.
- Parent interface, if applicable.
- Implementation details.
- Dependencies on existing tools.
- Integration requirements.
- Mathematical or behavioral assumptions.
- Required software and mathematical tests.
- Description of the capability gap being addressed.

The specification must be completed before implementation begins.

## Step 3 — Define acceptance tests

Generate tests before implementing the extension.

Tests must cover:

1. **Interface correctness:** Inputs, outputs, types, and parent-class contracts.
2. **Functional correctness:** Expected outputs for known inputs.
3. **Mathematical correctness:** Analytical benchmarks, invariants, boundary conditions, or limiting cases where applicable.
4. **Integration correctness:** Compatibility with the existing runtime and components.
5. **Failure behavior:** Invalid inputs, infeasible conditions, numerical errors, and resource limits.

Reuse framework-maintained contract tests and independently verified benchmarks wherever available.

Do not weaken, delete, or rewrite required tests to make an implementation pass.

## Step 4 — Implement the extension

Implement the smallest component that satisfies the specification.

Requirements:

- Inherit the appropriate approved parent interface for framework components.
- Reuse existing registered utilities and algorithms.
- Do not duplicate existing numerical solvers or state-management functionality.
- Do not modify the trusted runtime, core interfaces, or validation rules.
- Keep new functionality isolated in its own module.
- Preserve type safety and explicit input/output contracts.
- Do not introduce new dependencies without approval.

If implementation requires changes to trusted interfaces or architectural assumptions, stop and request review.

## Step 5 — Execute validation

Run all applicable tests in an isolated execution environment.

Use `uv` for dependency management and the project's locked dependency versions.

Validate:

- Interface compliance.
- Unit tests.
- Mathematical benchmarks.
- Integration tests.
- Existing regression tests.
- Static analysis and type checks.
- Resource limits and execution restrictions.

Record test outcomes, failures, and diagnostics.

## Step 6 — Diagnose and repair

If validation fails:

1. Classify the failure as an implementation defect, numerical limitation, specification problem, or architectural incompatibility.
2. Automatically repair implementation defects when the intended behavior is unambiguous.
3. Rerun all relevant tests after each repair.
4. Limit automatic repair attempts.
5. Never silently change the experiment's scientific assumptions, objective functions, constraints, or acceptance thresholds.

Escalate unresolved failures for human review.

## Step 7 — Produce a validation report

The report must contain:

- Extension name and version.
- Capability gap addressed.
- Existing components reused.
- New functionality implemented.
- Tests executed and their results.
- Mathematical verification evidence.
- Known limitations.
- Dependencies and execution environment.
- Any unresolved assumptions or failures.

Passing automated tests is necessary but not sufficient for declaring the extension scientifically valid or safe for unrestricted execution.

## Step 8 — Register the extension

After passing validation, the extension may be used in an isolated experimental run.

Promotion into the reusable component registry requires review of:

- Interface compliance.
- Test adequacy.
- Mathematical and behavioral assumptions.
- Compatibility with existing components.
- Scope of supported use cases.
- Security and dependency requirements.

Registered components must retain their validation evidence, supported capabilities, and limitations.

## Non-negotiable rules

- Prefer reuse over new implementation.
- Never silently modify trusted framework code.
- Never invent missing scientific assumptions without disclosure.
- Never treat numerical convergence alone as proof of mathematical correctness.
- Never treat self-generated tests as sufficient independent validation.
- Never execute untrusted generated code directly in the host controller.
- Never register a new component solely because its generated tests pass.

The objective is to expand the toolkit through small, tested, reusable capabilities—not to create a separate bespoke simulation engine for every new experiment.