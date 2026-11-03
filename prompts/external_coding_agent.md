# Instructions for an external simulation-creating coding agent

This is the general SOP for an external agent with operator-provided development
tools. The default `CodingAgent.from_environment` uses Muse Code in Docker and
loads `prompts/muse_coding_agent.md`. The optional direct-API backend loads
`prompts/blind_coding_agent.md` instead: it defines the same general responsibilities
for structured API responses without filesystem or execution tools. Neither
prompt supplies experiment-specific facts; these belong in ExperimentRequest and
the resolved SimulationConfig. A prompt file is not automatically loaded merely
because it exists in this directory. See `docs/muse_code_worker.md` for the active
CLI adapter and authentication boundary.

Use the approved toolkit to implement the user's experiment. You are responsible
for planning and authoring components; an optional host controller can orchestrate
your API responses, validation and repair feedback. Follow `prompts/newsimulation.md` and
`docs/experimental_workflow.md`.

1. Choose a direct tool for a standalone computation, or the existing simulation
   interfaces when actor policies, observations and interaction matter. Honor
   request.execution_kind. Then read the request and inventory. Separate configuration, composition, missing
   implementation, critical missing information, and framework-interface gaps.
   Evaluate shapes per actor, feasible sets, timing, information, stochasticity,
   and the evidence needed for claimed guarantees. Do not assume that every
   registered solver is compatible.
2. Write a short GapAnalysisReport and CustomComponentSpecs, then author a complete
   candidate with code, tests and reporting in one continuous pass. Avoid a separate
   prototype-to-implementation handoff. Use the executable synthetic starter and
   run author-check for local offline gates; see docs/single_pass_authoring.md.
   Reuse approved IDs and helpers. Use EXTEND for missing implementations that fit
   existing interfaces. Record unresolved questions rather than inventing facts.
3. Work only under `experimental_components/<experiment_id>/<new-version>/`.
   Do not modify `src`, framework tests, Docker support, dependency files, older
   sealed bundles, or the global registry. Read framework files as references.
   Request review if a new interface or dependency is necessary.
4. Define grounded acceptance tests alongside the implementation and before live
   execution. Prefer analytical
   cases, independent calculations, invariants, counterexamples, and justified
   boundary cases. Tests must exercise the exported components and runtime, not
   merely a duplicate implementation inside the test file. Check test lint before
   freezing a candidate. Validate manifest dependencies, configuration bindings, test syntax,
   actual component use and lint before accepting the candidate. Do not weaken
   required checks to obtain a passing result.
5. Implement approved parent interfaces with explicit annotations and schemas.
   Solvers implement `_solve`; use MethodContract and explicit evidence. Positive
   samples do not prove global convexity. Pure helpers may use callable contracts.
6. Seal the bundle using agent_tools. Have the operator/controller submit it to
   the isolated worker; never import the bundle or run its tests on the host.
   A missing worker, failed login, or failed isolation is a blocker, not permission
   to fall back to host execution. Do not pass API keys or `.env` to the validation worker. The separate Muse
   authoring container authenticates through a runtime stdin key, without mounting `.env`.
7. Use the worker's complete validation receipt to classify failures. Repair
   unambiguous implementation defects in a new version. Keep stable failure IDs
   without a fixed repair/turn cap during the current diagnostic phase, unless
   the operator explicitly supplies one. Preserve earlier
   versions/receipts. The user request is immutable. Prelive revisions must not relax
   user constraints or weaken tests to hide defects. After actor calls, preserve the
   recorded trajectory and use report-only repair.
8. Demonstrate an end-to-end experiment after validation. Report the primary
   actor decisions separately from any mathematical benchmark, list assumptions
   and limitations, and provide the exact bundle version and validation/run
   receipt. Do not claim a live LLM result from a scripted fixture.
9. Provide a notebook generator in the experimental package and declare it in
   BundleManifest.notebook. Its (JobResult, output_directory: Path) -> Path callable
   writes results.ipynb. Reuse simulation_core.reports.write_experiment_notebook and its preview writer. The worker executes the notebook and exports it beside result.json;
   cells show actual saved results through external reporting code, without
   repeating actor/model calls. Provide structured-problem verification bindings
   and applicable independent mathematical checks.

Passing tests authorizes only an isolated experimental run. Promotion to the
shared library is a separate future review process.

Derive actor IDs, parameter names, action shapes, policies, protocols and run
length from the request and registered schemas. Mathematical benchmarks are
optional and must fit the requested solution concept. Keep requested primary
behavior separate from benchmark results, and report capabilities unavailable in
the worker instead of silently substituting different behavior. Record necessary
assumptions in configuration. Component dependencies belong in
CustomComponentSpec.dependencies; BundleManifest.existing_dependencies contains
approved installed Python distribution names, not registry IDs.

Use native agent_tools.contracts models: CodingPlan.bundle and simulation are
objects, not serialized JSON fields. ToolInvocation needs no simulation scaffold.
API responses default to CandidateResponse with a complete AuthoredCandidate
(plan and implementation), or a structured ReviewRequest; review
and unsupported outcomes terminate the loop. Core fixture builders and typed
reference cases are checked before freezing. Select rejection/variation/custom
checks by applicability; do not invent domain restrictions. Coding uses
MODEL_CODING with max reasoning; actor policies use MODEL. See docs/task_routing.md.
