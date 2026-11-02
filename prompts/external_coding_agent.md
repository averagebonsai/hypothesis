# Instructions for an external simulation-creating coding agent

Use the approved toolkit to implement the user's experiment. You are responsible
for planning and authoring components; the toolkit does not generate or repair
code for you. Follow `prompts/newsimulation.md` and
`docs/experimental_workflow.md`.

1. Read the request and inventory. Separate configuration, composition, missing
   implementation, critical missing information, and framework-interface gaps.
   Evaluate shapes per actor, feasible sets, timing, information, stochasticity,
   and the evidence needed for claimed guarantees. Do not assume that every
   registered solver is compatible.
2. Complete a GapAnalysisReport and CustomComponentSpecs before implementation.
   Reuse approved IDs and helpers. Use EXTEND for missing implementations that fit
   existing interfaces. Record unresolved questions rather than inventing facts.
3. Work only under `experimental_components/<experiment_id>/<new-version>/`.
   Do not modify `src`, framework tests, Docker support, dependency files, older
   sealed bundles, or the global registry. Read framework files as references.
   Request review if a new interface or dependency is necessary.
4. Define grounded acceptance tests before implementation. Prefer analytical
   cases, independent calculations, invariants, counterexamples, and justified
   boundary cases. Do not weaken required checks to obtain a passing result.
5. Implement approved parent interfaces with explicit annotations and schemas.
   Solvers implement `_solve`; use MethodContract and explicit evidence. Positive
   samples do not prove global convexity. Pure helpers may use callable contracts.
6. Seal the bundle using agent_tools. Have the operator/controller submit it to
   the isolated worker; never import the bundle or run its tests on the host.
   A missing worker, failed login, or failed isolation is a blocker, not permission
   to fall back to host execution. Do not pass API keys or `.env` to the worker.
7. Use the worker's complete validation receipt to classify failures. Repair
   unambiguous implementation defects in a new version. Keep stable failure IDs
   and at most two repair attempts per identified failure. Preserve earlier
   versions/receipts. Scientific assumptions, required tests, constraints,
   objectives, or acceptance thresholds need explicit review to change.
8. Demonstrate an end-to-end experiment after validation. Report the primary
   actor decisions separately from any mathematical benchmark, list assumptions
   and limitations, and provide the exact bundle version and validation/run
   receipt. Do not claim a live LLM result from a scripted fixture.

Passing tests authorizes only an isolated experimental run. Promotion to the
shared library is a separate future review process.
