# Fresh live allocation trial: results and review

**Outcome: not accepted.** Intermediate candidates executed the supplied
simulation, independent numerical checks and results notebook successfully inside
the framework integration test. No candidate passed every required gate, so no
approved job result or executed notebook was exported. The final candidate
regressed. This report records the trial; it implements no subsequent improvements.

## Execution record

| Item | Recorded value |
| --- | --- |
| Experiment ID | `allocation_live_8f8bf161` |
| Coding model | `muse-spark-1.3-contributor` |
| Reasoning setting | `minimal`, as configured by the existing CodingAgent |
| Start / end, UTC | 2026-11-02 03:08:34 / 03:27:55 |
| Duration | Approximately 19 minutes 21 seconds |
| Coding-call or repair-count limit | None |
| Completed model responses | 25: 14 planning, 11 implementation/repair |
| Interrupted attempt | Call 26; no response/usage received |
| Retained source versions | `v1` through `v11`, all sealed |
| Provider-reported input tokens | 1,134,238 across completed responses |
| Provider-reported output tokens | 102,159 across completed responses |
| Planning share | 603,134 input and 67,737 output tokens |
| Implementation share | 531,104 input and 34,422 output tokens |
| Worker image | `sha256:92cb1423f6ae8c3a54fab90143b0e334c792965024bb1389cc213bf5518d3719` |
| Framework digest | `57542d3856dbd5d2e6d432a45342d13bd2b4a0e095288c4b85d511bfe40c66a2` |

These token totals exclude unknown usage from the interrupted request and are not
a price estimate. There were no automatic provider transport retries. The LLM was
the coding agent; the simulated actor used the supplied scripted action.

## Isolation and absence of historical experiment access

The controller used only `experiment_requests/allocation.json` as experiment
input, a fresh namespace/audit directory and the current general blind prompt.
It did not resume a previous trial. The model received 25 explicitly allowlisted
toolkit source files plus discovery metadata, without filesystem, shell, web,
retrieval or execution tools. It received no controller conversation.

Before calling the API, the initial payload was checked for both prior experiment
names, the old projection-helper marker and old response/provenance identifiers.
Historical experiment implementations, tests, reports, saved notebooks and results
were excluded. Approved reusable toolkit components remained available.
The worker image build context was separately checked: it contained trusted
framework code/tests and the blind prompt, not historical experimental bundles,
request folders, reports, notebooks, credentials or Git data. The worker container
had no repository mount or network access.

All 26 saved requests were subsequently checked to contain identical curated
toolkit context and instructions. No prior-bundle paths or checked historical
provenance markers appeared. Repair context contained the model's own artifacts
and this trial's diagnostics. The model independently derived candidate answers
in its own tests; those were not supplied from an earlier experiment.
The transport checked that the actual credential never entered the model payload.
It supplied no tools, historical conversation IDs or previous-response IDs and
requested no response storage. Credentials remained host-side.

Every retained version's file hashes match its seal. Implementation source bytes
match the respective actual model response, and all versioned tests match the
accepted frozen plan. No manual source/test fixes were applied. End-of-trial
hashes confirmed the framework, prompts, trusted tests, dependency files and both
previous experiment directories were unchanged. This establishes what this trial
exposed; it does not establish a provider model's pretraining history.

## Task and mathematical reference

The user problem was to allocate a budget across nonnegative vector coordinates,
maximizing negative squared distance from a desired allocation. The supplied case
used budget 10, target `(8, 6)` and primary scripted action `(5, 5)`. A separate
mathematical benchmark was required, alongside support for other budgets, targets
and dimensions. The system prompt contained no allocation-specific defaults.

For this supplied case:

| Quantity | Value implied by the original problem |
| --- | --- |
| Primary action | `(5, 5)` |
| Primary payoff | `-((5-8)^2 + (5-6)^2) = -10` |
| Mathematical optimum | `(6, 4)` |
| Optimal payoff | `-8` |
| Available payoff improvement | `2` |

The framework integration test reached and passed problem-derived feasibility,
objective and independent SLSQP comparisons in `v6`–`v10`, then successfully
generated and executed the notebook. This supports the fixed-case computation.
Those were integration-test executions, not exported approved-run artifacts; the
worker discarded the temporary notebook when other acceptance tests failed.

Five private input-only robustness cases were declared while planning was still
in progress, with different budgets, negative targets and two-, three- and
four-dimensional vectors. They were never sent to the coding model and never run,
because no submission passed all primary gates. Consequently, this trial does
not establish generalization across those cases or arbitrary unfamiliar problems.
SLSQP agreement is a numerical cross-check, not a universal optimality proof.

## What the model reused and created

The model reused the scripted policy, simultaneous protocol, trusted runtime,
canonical event/replay machinery, benchmark runner, method contracts and the new
independent verification interface. It initially used MechanismGameView, then
implemented a BestResponseGameView adapter after receiving a benchmark error.
It reused `simulation_core.reporting.write_results_notebook` through its own
experiment-local generator. No new dependency installation was needed.

It created an allocation payload schema, mechanism, game view, solver, projection
helper, notebook generator, seven acceptance tests and experiment metadata/config.
The projection algorithm was independently authored as a sorting/water-filling
method rather than delegated to SciPy. That is a reasonable model-specific
analytical choice; correctness still depends on implementing the same constraints
in the mechanism and validating more than one feasible fixture.

## Progress and failures

| Calls / versions | Observation |
| --- | --- |
| Planning 1–8 | Extra/missing manifest fields, missing method contract, malformed nested JSON, test syntax and missing configuration field |
| Planning 9–13 | Remaining failures were import layout; full regeneration repeatedly reintroduced formatting errors |
| Planning 14 | Static plan review passed and tests/configuration froze |
| Call 15 / v1 | Lint/type failures and strict-tuple MethodContract construction prevented test collection |
| Call 16 / v2 | Tests ran; list/tuple transport failures in generated fixtures and payload validation |
| Call 17 / v3 | mypy passed; benchmark required a finite-action or best-response interface |
| Call 18 / v4 | Added best-response interface but introduced a circular import |
| Call 19 / v5 | Separated projection helper; framework reached notebook generation, which corrupted JSON through raw text replacement |
| Call 20 / v6 | Notebook fixed using parsed JSON; framework integration passed; agent explicitly requested a frozen-test/spec revision |
| Calls 21–24 / v7–v10 | Framework integration kept passing; frozen-test and lint failures persisted |
| Call 25 / v11 | Added a self-import in schemas.py, regressing mypy and test collection |
| Attempt 26 | Interrupted for specification review |

| Validation | v1–v2 | v3–v5 | v6–v10 | Final v11 |
| --- | --- | --- | --- | --- |
| Ruff | Failed | Failed | Failed | Failed |
| mypy | Failed | Passed | Passed | Failed |
| Framework integration | Failed | Failed | Passed | Failed at collection |
| Full acceptance stage | Failed | Failed | Failed: six failures, two passes | Failed at collection |
| Trusted regressions | Passed | Passed | Passed | Passed |

Worker regression receipts reported 227 passed and one skipped. This is framework
health evidence, not evidence that the new extension passed acceptance.

### The frozen tests were not executable as written

Generated helpers invoke `WorldConfig.model_validate` and
`SimulationConfig.model_validate` with Python lists for strict tuple fields.
The core correctly rejects these before the generated mechanism is called.
The request/config transport uses JSON validation and does not have that failure.
Implementation changes cannot legally alter how an unchanged core model validates
a literal dictionary inside a frozen test. Core monkeypatching would violate the
experiment rules. Static syntax/lint/component-use checks missed this problem.

### The tests also encoded an incorrect scientific expectation

`test_mechanism_scores` and `test_game_view_evaluates` assert payoff `-18` for
`(5,5)`, contradicting the original objective's `-10`. Those assertions were masked
by earlier fixture failures; simply repairing transport would reveal them.
The generated scoring formula itself remained the correct negative squared
distance. Later model summaries nevertheless repeated the incorrect `-18` claim.
Narrative summaries must therefore not be treated as the experiment record.

### A legal termination condition was not represented in the controller

Response 20 explicitly stated that a frozen test/spec revision was needed.
The controller still required another implementation and continued the loop.
Its response contract has no structured needs-review terminal state, and the
workflow does not interpret that summary as a stop condition.

I interrupted the dedicated process for review, not because of a coding-turn
limit. Manual shutdown was delayed by failed stop-control checks/process
identification, allowing additional attempts; that delay was an operator-control
issue, not a model mistake. The final audit records 25 completed responses and
the interrupted 26th attempt. No scientific tests or framework rules were changed.

## Additional findings from static review

1. **Missing feasibility enforcement.** Even in the intermediate versions whose
   integration test passed, `AllocationMechanism.validate_actions` checked action
   count/kind and vector dimension, but not nonnegativity or sum equal to budget.
   The independent verifier checked the actual feasible primary and benchmark
   actions. It did not establish rejection of invalid actions. This is a source
   inspection finding; no post-trial counterexample simulation was run.
2. **Claims and evidence diverged.** Summaries repeatedly claimed import sorting
   was fixed while Ruff continued to reject it. Some summaries described the
   primary score incorrectly. The final revision was worse than earlier ones.
3. **Notebook support partly succeeded.** The model wrote a generator and repaired
   a real JSON corruption bug. Framework checks executed the resulting notebook
   successfully. The separately generated notebook test only checked file
   existence and itself failed during fixture construction. No notebook was
   preserved for inspection because the accepted-run export path was never reached.
4. **Schemas were sometimes descriptive metadata.** For example, the notebook
   utility input/output schema dictionaries used descriptive keys instead of
   meaningful JSON Schema constraints. Nonempty dictionaries are insufficient to
   establish typed input/output contracts.
5. **Reuse remained incomplete.** The game view eventually duplicated shared
   snapshot/evaluation plumbing instead of composing the shared adapter with the
   required best-response capability. It also retained a silent budget default of
   10 in a problem where the budget should come from required configuration.

## Recommended modifications, not implemented

**First, repair the planning/test boundary.** Represent reference cases as typed
data and validate expected feasibility/objective values against ProblemStatement
before freezing them. Provide validated fixture builders for core models. Exercise
test scaffolding through the correct JSON boundary in isolation. Keep scientific
intent fixed while permitting an explicitly reviewed correction of broken test
plumbing. A wrong numerical expectation requires a reviewed scientific correction,
not a silent implementation workaround.

**Second, make review a terminal response.** Add a structured completed / needs
review / unsupported outcome to authoring responses. Stop or return control when
a frozen requirement is inconsistent; retain the specific evidence and receipts.
This does not require reinstating arbitrary turn caps. Preserve earlier partially
successful versions and detect regression rather than assuming the latest version
is best.

**Third, separate mechanical edits from scientific authoring.** Use a deterministic,
audited formatting step before freezing/sealing, with explicit raw-versus-derived
artifact provenance. Avoid spending repeated model calls on blank-line changes.
Support focused per-file/per-field revisions so an import repair cannot silently
rebuild the entire plan or introduce a self-import. Any transformation still needs
validation and must not conceal changes to scientific behavior.

**Fourth, strengthen problem-level verification.** Test rejection of negative,
over-budget, wrong-dimension, nonfinite and otherwise infeasible actions, rather
than checking only feasible outcomes. Verify that mechanism and solver use the
same domain. Run predeclared private parameter/dimension cases once primary gates
pass, with no reference answers or feedback returned to the coding model.

**Fifth, simplify the authoring representation and discovery contract.** Replace
large JSON-inside-string plan fields with provider-compatible typed structures
where possible. Validate open schema documents as actual contracts or derive
them from exported Pydantic models. Advertise the continuous benchmark's required
best-response capability explicitly. Distinguish mathematical method contracts
from ordinary reporting utilities; a notebook generator should not need a
mathematical guarantee merely to satisfy a generic utility classification.

**Sixth, retain diagnostic results without approving them.** Preserve completed
primary results, benchmark verification and executed notebooks from failed
integration attempts, clearly marked unapproved and tied to source/image/input
hashes. That would let users inspect real progress even when an unrelated test
fixture blocks acceptance. Continue restricted exports for private state.

**Finally, measure efficiency and model settings.** The model repeatedly received
roughly 40–50 thousand input tokens per call. Use allowlisted source retrieval,
smaller revision payloads or compatible caching without exposing past experiments.
Make reasoning effort configurable and assess it with controlled repeated trials;
this run tested the current `minimal` setting, not every possible model setup.

## Assessment and retained evidence

The toolkit supported an independently authored domain extension and a complete
fixed-case integration execution with mathematical cross-checks and a notebook.
Isolation, immutable versions, per-stage validation and independent checks gave
useful evidence. The complete authoring task nevertheless failed: malformed
frozen tests, persistent lint failures, missing constraint validation and failure
to terminate for review prevented a reliable deliverable.

Removing turn caps allowed substantial repairs, but also prolonged an unsatisfiable
repair loop and introduced a later regression. This is one trial, not 25 independent
success/failure samples. It does not identify a model-wide success rate or establish
that any single prompt/tool change caused the observed behavior.

Exact requests/responses, preflight allowlists/hashes, planning diagnostics,
per-version worker receipts, the interruption explanation and the private
input-only evaluation specification remain locally under
`experimental_components/_authoring/allocation_live_8f8bf161/`, with owner-only
JSON permissions and Git ignored. Sealed source/tests/configuration remain in
this directory's version subfolders. The worker is stopped. Only this report and
audit explanation were added after termination; no recommended improvement,
framework change or experiment repair was implemented.
