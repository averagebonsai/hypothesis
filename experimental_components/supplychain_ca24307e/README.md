# Supply-chain trial: one decentralized run, nine days

This **operator-assisted trial** completed one live trajectory using Muse Code for
experiment authoring and separate LLM policies for the four supply-chain organizations.
It demonstrates a working simulation, not autonomous correctness or the requested
10–15 minute end-to-end speed. No coordinated scenario or replications ran.

## Open the results

- [Executed notebook](../_runs/supplychain_ca24307e/v2/c9c651ca0093486599ef9ea6f28251f0/results.ipynb)
- [Recorded result](../_runs/supplychain_ca24307e/v2/c9c651ca0093486599ef9ea6f28251f0/result.json)
- [Audited source bundle](v2/)
- [Aggregate operator audit](operator_metrics.json)
- [Live validation receipt](../_authoring/supplychain_ca24307e/live_receipt.json)
- [Resolved request](../../experiment_requests/supplychain_resolved.json)

The notebook contains background, recorded execution/results and six figures, one
decision-rationale section, prose assumptions, and limitations. Its cells call toolkit
reporting helpers and load the adjacent recorded result; they make no actor API calls.
Run reporting cells with this repository's environment and the notebook's directory as
the working directory. The notebook and result remain local, under the Git-ignored run
directory, because recorded results contain complete private states and actor traces.

## Who did what

**Muse Code**, running `muse-spark-1.3` with maximum reasoning inside Docker, wrote the
experiment mechanism, contextual policy wrapper, Pydantic schemas, mathematical bound,
measurements, event audit, notebook generator and tests. It produced both sealed v1 and
the repaired v2. The operator did **not** edit those generated experiment source files.

**The operator (the assistant in the parent conversation)** created root `AGENTS.md`,
resolved the user's scope into a typed request, supplied assumptions and role profiles,
and wrote local launch/preflight scripts. Before authoring, the operator also extended
the generic toolkit's treatment of declared standard-envelope LLM wrappers so their
model settings, budgets, behavior bindings and privacy/fallback checks remained active.
Key discovery already supported arbitrary numbered credentials; additional synthetic
tests covered pools of 1, 4 and 12 keys. Four distinct real credentials were available.

The operator reviewed v1 and interrupted deployment before any actor calls, then gave
Muse Code explicit repair instructions. These interventions are consequential: the
original authoring checks did not discover all the problems unaided. This trial must
not be described as an independent, end-to-end autonomous success.

## Isolation and execution

The original authoring worker used a fresh image/session with only approved generic
toolkit sources, the current request, and fresh input/workspace/home volumes. The image
probe, initial context scan and active mount inspection found no historical experiment
bundles, outputs, host workspace/home, `.env`, Git history or private evaluation tests.
[Isolation evidence](../_authoring/supplychain_ca24307e/active_isolation.json) is retained.

After interruption closed the original session, a fresh repair session received only
this trial's current candidate and the operator's feedback. This preserves current-trial
work rather than exposing a previous experiment's solution. It does mean the repair had
to reload the current candidate; it was not an uninterrupted authoring session.

Simulation actors used `muse-spark-1.3-contributor`. Credentials stayed in the host relay,
with no credential files mounted into generated-code workers. The deployed validation
worker was network-isolated. Each live request received a canonical filtered observation;
48 requests passed the recorded observation/privacy check. Suppliers acted concurrently
against the same precommit state. Other phases followed their causal dependencies.

The simulation used 36 committed phases: manufacturer orders, simultaneous suppliers,
logistics allocation, manufacturer production/settlement, repeated for nine days. That
is 45 decisions. There was exactly one live trajectory, with 48 API attempts: 44 accepted
model actions, four rejected responses, and one configured fallback action.

## What required repair before live execution

1. V1 delivered incoming shipments after the manufacturer's ordering decision. V2 enters
   each new day's ordering phase with that day's arrivals already in private inventory.
   Closing holding costs are calculated before preparing the following day; day-nine
   dispatches remain in transit to day ten.
2. V1 allowed shipment offers above accepted orders and clamped backlog subtraction.
   V2 enforces offers ≤ accepted quantity ≤ outstanding orders, as well as stock and
   transport limits. Contextual policy checks and authoritative mechanism checks both
   enforce these constraints; validated dispatches decrement backlogs exactly.
3. V1 omitted several own-role economic terms from observations. V2 exposes those terms
   to their owners while withholding other organizations' private costs and stocks.
4. V1 tests read a scratch `draft.json` that was present in authoring but absent from the
   deployed bundle. V2 supports deployed manifest locations and tests portable loading.

V1 passed its local authoring gate, illustrating that a ready flag is not a semantic
correctness certificate and that the local gate did not fully reproduce deployment.
The sealed versions and [repair feedback](../_authoring/supplychain_ca24307e/prelive_repair/operator_feedback.json)
remain available for comparison.

## Observed results

| Day | Transport capacity | A / B dispatched | Products sold | Lost sales | Consolidated profit |
|---|---:|---:|---:|---:|---:|
| 1 | 200 | 80 / 80 | 80 | 0 | $5,060 |
| 2 | 200 | 80 / 80 | 80 | 0 | $5,100 |
| 3 | 80 | 40 / 40 | 80 | 0 | $4,340 |
| 4 | 80 | 40 / 40 | 80 | 0 | $5,380 |
| 5 | 80 | 40 / 40 | 70 | 10 | $4,590 |
| 6 | 80 | 0 / 80 | 40 | 40 | $2,040 |
| 7 | 200 | 160 / 40 | 0 | 80 | −$3,240 |
| 8 | 200 | 20 / 180 | 80 | 0 | $5,770 |
| 9 | 200 | 100 / 20 | 80 | 0 | $6,270 |

Total sales were **590/720 (81.9%)**, with **130 lost sales** and **$35,310** consolidated
operating profit. Role profits were manufacturer $20,310, Supplier A $6,320, Supplier B
$6,360, and logistics $2,320. Procurement and freight transfers cancel in consolidated
profit. Initial inventory costs are sunk, and there is no terminal salvage value.

Capacity restoration on day seven did not immediately restore production. Supplier A's
day-six decision exhausted two attempts and used its declared zero-action fallback.
With no A offered, logistics sent only B; the manufacturer consequently lacked A on day
seven. The day-seven A-heavy allocation arrived on day eight. Full fulfillment resumed
on days eight and nine, but the required three-day streak could not be confirmed by
day nine. Recovery is therefore **not observed within the horizon**.

The notebook's 710-unit mathematical figure is a valid but loose optimistic physical
upper bound. It ignores prefix timing and is neither an attainable optimum nor an
equilibrium. The gap from 710 must not be interpreted as a quantified coordination
loss. In particular, the fallback is a technical validation outcome that materially
affected service; this is not a clean behavioral-only comparison.

## Validation and timings

The final deployed worker passed lint, types, **63 acceptance tests** (62 generated
tests plus the toolkit composition contract), **318 toolkit regressions with two
skipped**, declared acceptance coverage and composition. Required recorded checks
verified canonical observations/privacy and the generated supply-chain audit. Optional
generic numeric-problem checks were unverified/unsupported; those are not claims of
an independently certified economic optimum.

The operator separately recomputed daily inventory conservation, demand fulfillment,
shipment and production limits, consolidated external cash flows and role-profit sums
using recorded JSON only. This audit passed. No generated code was executed on the host.
Terminal in-transit stock is 100 A plus 20 B, not prematurely consumed.

| Stage | Measured time |
|---|---:|
| First complete candidate | 26.6 min |
| Original preparation, preview/review and interrupted validation included | 28.6 min |
| Focused repair authoring | 13.8 min |
| Repair including deployed validation and preview | 15.4 min |
| Final live worker, including checks and notebook | 19.7 min |
| Actual simulation within final worker | 18.5 min |
| Final-worker regressions | 46 sec |
| Final notebook rendering | 4.6 sec |

From initial start to completed live report was approximately **67.6 minutes**, including
operator review, interruption and repair setup. The 10–15 minute end-to-end target was
not met. First-pass activity recorded 49 inspections and 91 writing tools; observed gaps
include model deliberation and event delivery, not exact tool execution durations.
The author created several thousand lines across sources and tests.

Across 48 live API attempts, median request time was 28.45 seconds and maximum was
92.72 seconds. Reported usage totaled 66,599 input and 146,273 output tokens; visible
rationales are much shorter than the reported output-token counts. This usage alone
does not distinguish hidden reasoning from other provider accounting. Four credential
slots handled 13/12/12/11 requests; maximum credential wait was about 0.00011 seconds.
Keys were not the bottleneck. Supplier concurrency saved time, but the 36 dependent
phases still impose a long critical path.

## What should be fixed next (not implemented after this run)

- **Give actionable retry feedback.** `LLMPolicy` currently changes only `retry=true`;
  it does not include the rejected action or concrete validation error. Supplier A
  repeated `fulfill=200, ship_request=240` and exhausted its attempts. Return sanitized
  field/bound errors and the previous proposal within an explicitly permitted retry
  envelope, preserving canonical observations and privacy checks. Record useful
  validation details instead of only `schema_or_json_validation`.
- **Make dynamic feasibility explicit before a call.** Put current action limits and
  relationships in a reusable observation-local contract. Pydantic validators enforce
  the relation, but their dynamic constraints are not automatically in JSON Schema.
  This should reduce rejected proposals without clamping or hardcoding actor decisions.
- **Close the local/deployed test gap.** Test only packaged artifacts under the same
  manifest paths and working-directory rules as deployment. Do not let scratch files
  make a candidate appear ready. Static test-link heuristics also caused repair churn;
  improve helper/fixture recognition without accepting vacuous assertions as evidence.
- **Add a prelive semantic review gate for timing, orders and information.** Current
  notebook review and self-authored tests missed errors that operator review found.
  Treat an independent reviewer/checker as a separate source of evidence rather than
  describing a model's own tests as independent certification.
- **Reduce unnecessary authoring and actor inference work.** Measure inspection and
  source-generation size, encourage targeted repairs, and make actor inference effort
  an explicit, tested execution setting separate from maximum coding-agent reasoning.
  Do not promise that more credentials can accelerate sequential dependencies.
- **Improve interpretation.** The notebook should foreground how the fallback caused
  the day-seven stockout, break its dense results paragraph into readable explanations,
  and describe the mathematical reference's weakness. A single baseline cannot identify
  coordination effects or compare replication consistency.

No post-run experiment-code or architecture improvements were applied. The results and
generated notebook are preserved as produced, with this operator review alongside them.
