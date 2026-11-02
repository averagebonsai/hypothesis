# Blind live coding-agent trial

**Outcome: failed validation. No completed simulation result is claimed.**

This trial called `muse-spark-1.3-contributor` through the configured live Meta API.
It was separate from the earlier `vector_allocation/v1` trial, whose experiment
code had been authored by the interactive assistant without a separate model call.
Here, the model generated its own plan, tests, and implementation from a fresh
problem statement and a curated toolkit inventory. The interactive assistant
implemented the orchestration, problem schemas, isolation and audit mechanisms;
it did not write or repair the submitted experiment code/tests.

## Supplied problem and expected behavior

[problem.json](problem.json) retains the actual request sent to the model: choose
a nonnegative vector with total budget 10, minimizing squared distance from target
(8, 6), equivalently maximizing negative squared distance. The simulated actor's
supplied fixture is (5, 5). The mathematical benchmark must be separate from this
primary decision. Other budgets, target values, and dimensions must work too.
No optimal allocation or expected payoff was supplied as a reference answer.

The LLM's role was **coding agent**. The eventual simulation actor would have used
the requested scripted fixture. This was not a live LLM policy choosing allocations.

The structured request uses the new `ProblemStatement`, `VariableSpec`,
`ObjectiveSpec`, `ConstraintSpec`, and expression models. These describe the
problem, rather than prescribing a projection algorithm or a solver class.

## What the model saw

`CodingAgent` injected [the blind instructions](../../prompts/blind_coding_agent.md)
and the explicit source allowlist in
[authoring.py](../../src/agent_tools/authoring.py). It supplied the general core
parents, types, runtime/contracts, discovery inventory, existing scripted policy,
simultaneous protocol, recording mechanism, and scalar-search helpers. Installed
NumPy/SciPy were available for reuse. No new package was installed for the model.

The model received no filesystem, shell, retrieval, network, or execution tools.
It could only return structured text. The API context excluded:

- All prior experimental bundles and reports, including `vector_allocation/v1`.
- Existing tests, notebooks, documentation, Git history, and this conversation.
- `.env`, API keys, controller code, and the private evaluation/reference solver.

The first request was checked for `vector_allocation`, `project_simplex`, the old
trial path and provenance marker: none occurred. Exact source hashes and payloads
are retained. Later repair calls contained only the model's own earlier artifacts
and validation diagnostics. Consequently, an answer derived by the model in its
own tests could appear in its later context; it was not supplied from old results.
This controls information sent by this trial; it cannot establish what a provider's
pretrained model already knows about standard mathematical algorithms.

The old trial was retained rather than deleted. Both context construction and the
worker build use allowlists; the worker has no repository mount. Only this trial's
sealed bundle was staged into its restricted execution container. The trusted
image contains framework tests and the blind prompt, but no historical bundles.

## Actual calls and artifacts

| Call | Purpose | Result |
| --- | --- | --- |
| 1 | Plan and tests | Invalid manifest fields; no bundle executed |
| 2 | Correct plan formatting | Plan accepted and frozen |
| 3 | Initial implementation | Rejected artifact path `experiment_extension/README.md` |
| 4 | Correct artifact path | Retained as `v1`; failed validation |
| 5 | Repair implementation from diagnostics | Retained as `v2`; still failed validation |

Provider-reported usage totals **204,239 input tokens and 13,625 output tokens**
across five calls. The complete curated source was resent with each stateless
request. These are token counts, not an estimated price. Provider response IDs:

```text
resp_6ae7da1ef5ac4dcbf2894ec0
resp_6ae7da2e0894d2853fa340d9
resp_6ae7da40b79fac80d5824dc4
resp_6ae7db52814d08c0ac1b4c43
resp_6ae7db913444fae9a7b54c25
```

The adapter allowed five calls total: planning, one plan-format correction, initial
implementation and at most two implementation repairs. The path rejection used
the first implementation repair. Restart/resume preserved consumed calls and
checked that toolkit context and instructions matched the original audit.

The model created an allocation payload schema, mechanism, game view, solver,
seven tests, registration metadata/configuration, and README. It independently
chose a water-filling/simplex-projection algorithm, rather than reusing SciPy's
optimizer. Standard toolkit components supplied scheduling, scripted actions,
runtime/state/replay, configuration validation and benchmark infrastructure.
The host materializer inserted the authoritative request, version and repair-count
metadata; it did not change the model's scientific configuration, tests or code.

See the untouched sealed [v1](v1/README.md) and [v2](v2/README.md) artifacts.
Their READMEs are model-authored descriptions, not evidence that their claims pass.

## Verification and limitations

Final revalidation of unchanged `v2`, after correcting a worker packaging defect:

| Check | Result |
| --- | --- |
| Ruff on generated code and tests | Failed: import formatting, unused test import, implicit string concatenation |
| mypy on generated implementation | Passed |
| Seven model-authored tests | Passed, but inadequate: they test local formulas/helpers, not the generated components |
| Framework-owned extension integration test | Failed: `simultaneous.v1` was declared as a Python package dependency |
| Trusted framework regression suite | Passed |
| Main simulation / independent held-out evaluation | Not run because validation failed |

The initial worker image omitted the blind prompt needed by a new framework test.
That was a harness packaging error, not a model error. Packaging was corrected to
copy only that prompt, then the original `v2` bytes were revalidated. The final
receipt uses image
`sha256:5b62488ca70b8052725fbbd34a91f4a3c43f42fea75bd1d2dccd5d14a849ca64`.
Later trusted framework changes require rebuilding; that image identifies the
specific revalidation, not a permanent current image.

The frozen plan's `existing_dependencies` field lists component IDs instead of
installed Python distribution names. The worker correctly rejects this before
experimental registration. That blocks assessment of downstream integration and
mathematical correctness. Passing mypy or the self-tests does not establish those.

No implementation, frozen test, manifest dependency or validation threshold was
patched to manufacture success. No additional calls were made after the repair
budget was exhausted. The private reference/probe phase was never reached, and
there is no live experiment payoff/optimum comparison to report.

## Retained audit and next improvements

Exact request/response JSON, source/prompt hashes, usage, and validation receipts
remain locally under
`experimental_components/_authoring/allocation_trial/ee5e45aee4b84d74af7fdac368f6ba5a/`.
The final receipt is `post-harness-validation.json`. Audit/worker receipts are
owner-readable/writable and ignored by Git because they may contain private input.
The public versioned bundles and this report retain the reviewable outcome.

Before the next trial:

1. Separate component dependencies from Python distributions in the planning
   schema, and check approved package names before freezing a plan.
2. Validate test syntax/lint during planning, and reject tests that do not exercise
   the submitted components. Freezing a broken test scaffold makes code-only
   repairs unable to pass, even when fixing formatting would preserve intent.
3. Keep framework-owned integration tests and add independent problem-derived
   checks of objectives, feasibility, primary-action preservation and benchmark
   output. Execute private parameterized comparisons only after required gates
   pass, with no reference answers or evaluation feedback sent to the model.
4. Reduce source context through dependency-aware selection while keeping exact
   interfaces available. This trial's repeated full inventory was expensive.

These are findings from a failed end-to-end attempt, not claims that a general
coding agent has already solved unfamiliar experiments reliably.
