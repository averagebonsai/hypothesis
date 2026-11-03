# Three-actor public-goods trial with concurrent credentials

The fresh Muse Code agent built the experiment, and the live trajectory completed
six rounds with **18 actor requests, no retries, no replays and no errors**.
All three distinct actor credentials were used successfully. Open the
[reviewed executed notebook](../_runs/public_goods_fast_faae5470/v2/reviewed/results.ipynb).

The live simulation took **4 minutes 39 seconds**. The first executed notebook was
ready **27 minutes 20 seconds** after starting trial preparation. This missed the
10–15 minute construction-plus-execution target. Subsequent operator notebook
review and report-only corrections added time; they did not rerun actors.

## Experiment and actual behavior

Three participants started with zero savings and received 20 per round in rounds
1–3, then zero in rounds 4–6. The multiplier was two, funds carried over, and any
contribution up to available wealth was legal. Everyone knew the schedule upfront.
All actors had the same neutral own-final-wealth objective, through the new typed
behavior interface. The optional cooperative/opportunistic variant was not run.

| Round | p1 contribution | p2 contribution | p3 contribution |
| --- | ---: | ---: | ---: |
| 1 | 20 | 20 | 20 |
| 2 | 60 | 60 | 20 |
| 3 | 0 | 20 | 153.33 |
| 4–6 | 0 | 0 | 0 |

Final balances were **228.89, 208.89 and 115.56**, respectively. Total contributions
were 373.33 and group wealth was 553.33. The all-zero mathematical trajectory ends
at 60 each (180 total); full reinvestment ends at 2,240 each (6,720 total). The
latter is an alternative whole history, not a feasible unilateral final-round
deviation. The marginal private return was two-thirds throughout both phases.

The recorded rationales describe attempted reciprocity, partial free-riding and
failed coordination. In round 3, p1 withdrew cooperation, p2 contributed only the
fresh endowment, and p3 went all-in hoping to rebuild cooperation and benefit later.
p3's expectation did not match the simultaneous choices. Giving stopped afterward,
but disagreement already existed before withdrawal. A single trajectory cannot
separate withdrawal, horizon, wealth and belief effects. These explanations are
actor self-reports, not independently established motives. No deviation was scripted.

## Time and bottlenecks

| Section | Measured time |
| --- | ---: |
| Initial images and isolation | 43 seconds |
| First planning pass | 7 min 8 sec |
| Planning repair | 2 min 54 sec |
| Implementation | 3 min 45 sec |
| Preview content review | 42 seconds |
| Unnecessary experiment-author call for a toolkit failure | 36 seconds |
| Operator toolkit repair between worker attempts | about 4 min 51 sec |
| Corrected worker preparation | 8 seconds |
| Successful worker validation and transport overhead | about 49 seconds |
| Actual live play | 4 min 39 sec |
| Initial final-notebook execution | 4 seconds |

The initial failed validation and preview rendering add the remaining time before
the first completed artifact. The operator repair interval includes diagnosis,
implementation and checks, rather than model inference. Report-only rendering after
manual review took another 20 seconds, apart from the review itself.

Round durations were **32.7, 47.1, 125.3, 41.6, 19.2 and 12.4 seconds**. Individual
provider durations summed to 669.5 seconds while round wall time summed to 278.3
seconds: an overlap ratio of **2.4**. This demonstrates concurrency, not a controlled
counterfactual speedup measurement. The longest credential wait was below 0.1 ms;
credential availability was not the bottleneck in this run.

The slowest provider response took 125.2 seconds and reported 10,393 output tokens
for a 469-character visible decision. Across the run the provider reported 57,533
output tokens. This suggests substantial processing beyond the visible JSON, but
the existing response record does not separate reasoning tokens. Actor reasoning
was provider-default; coding-agent reasoning was explicitly maximum.

The largest end-to-end cost was authoring, especially interface inspection and
planning repair. Extra keys improved live throughput; they did not fix these costs.
A reliable 10–15 minute total still needs a shorter authoring path and profiling of
actor generation settings, while retaining the requested maximum coding reasoning
and no explicit generation-token ceiling.

## Isolation and provenance

The coding agent received only the new request and approved generic toolkit. Before
its first model call, the image was checked for absence of historical bundles,
results, trusted tests, `.env`, Git data and an existing session home. The three
session volumes were new. Active mount inspection confirmed only this trial's
read-only inputs, workspace and home; no historical or host-directory mounts existed.
The same Muse session persisted between stages. No previous experiment outcome or
implementation was supplied to the agent. Coding used Muse Code with
`MODEL_CODING=muse-spark-1.3` at maximum reasoning; actors used
`MODEL=muse-spark-1.3-contributor`.

The first validator failed before **any actor calls**, because a newly added toolkit
regression test tried to read an intentionally excluded host-only request file.
The operator repaired that test boundary and reran the **unchanged sealed v1 bundle**
with the corrected framework. Thus there were two worker attempts but only one live
trajectory. The initial `needs_review` outcome is retained rather than overwritten.
No coding agent was given previous-trial context during recovery.

Local ignored audit files are under `../_authoring/public_goods_fast_faae5470/`:
`isolation.json`, `active_isolation.json`, `stage-timing-*.json`, `phases.json`,
`validation-1.json`, `completed_validation.json`, `completion_timing.json`,
`independent_audit.json` and `reviewed_report.json`. Worker receipts and per-call
audits are under `../_runs/public_goods_fast_faae5470/v1/`.

## Code, checks and report corrections

The agent authored four source files: package initialization, mechanism/action
schema, reference functions and reporting. It supplied four test files. The final
primary worker passed **49 acceptance/composition cases and 305 framework cases**
(two skipped), Ruff and mypy. Canonical-observation verification checked all 18 model
requests. An independent data-only audit checked every contribution budget, payoff,
balance update and aggregate wealth identity. Optional generic numeric verification
reported unsupported/unverified; it did not claim a proof for this custom mechanism.

Operator review found a units mismatch in the original report: final reference
wealth was compared against a single-round observed payoff. The reusable report
interface now declares round versus cumulative payoff basis. The v2 report uses
cumulative values, clarifies mathematical scope and causal limitations, and removes
duplicate/technical assumptions. Only `report.py` changed among experiment Python
sources; scientific rules and recorded results are unchanged. Offline report
validation passed 48 frozen authored cases, Ruff, mypy and observation privacy,
with **zero actor calls**. The notebook contains all 18 original rationales once.

## Defaults and remaining work

Concurrent calls, streaming, durable checkpoints, credential leasing, waiting
heartbeats and schedule-derived budgets are now defaults. Additional numbered API
keys remain host-only; logs contain credential slot and wait time, never key values.
Cached trusted images are reused when their exact framework digest matches.

This trial also led to concrete fixes: static test review now follows shared
component aliases instead of rejecting valid instance-based tests, and a trusted
framework regression failure goes directly to toolkit review rather than asking the
experiment author to repair read-only scaffold code. These fixes were made after
the initial failure and before live play; this run does not measure their effect on
a fresh authoring attempt.

The next speed work should prioritize functional configuration/report starters,
early authoring checks before a CLI stage ends, and eliminating prototype rewrites
between planning and implementation. Actor generation should be measured separately
from credential wait. No additional live run was used to tune these findings.
