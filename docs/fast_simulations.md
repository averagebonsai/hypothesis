# Faster simulations and the next public-goods trial

The next live experiment has **not** been run. The prepared requests contain rules
and preferences, not past decisions, results or implementation code.

## Prepared inputs

- [Neutral request](../experiment_requests/public_goods_fast.json): three LLM actors,
  six simultaneous rounds, fresh endowment 20 in rounds 1–3 and zero in rounds 4–6,
  public-good multiplier two. Initial savings are zero, earnings carry over, and
  contributions may use all currently available wealth. Everyone knows the horizon
  and withdrawal schedule upfront. All three have the same neutral own-wealth goal.
- [Optional heterogeneous request](../experiment_requests/public_goods_fast_heterogeneous.json):
  identical rules, with cooperative tendencies for p1/p2 and an opportunistic
  tendency for p3. These are private instructions, not hardcoded actions. This is
  an alternative experiment, not a silent change to the neutral baseline.
- [Execution settings](../experiment_requests/public_goods_fast.execution.json):
  three concurrent requests, streaming, 180-second provider I/O timeout, no explicit
  generation-token ceiling, two attempts per decision, 12 attempts per actor and
  36 overall. There are 18 primary decisions; the budget reserves room for retries.
  Actor reasoning remains provider-default rather than guessing an unsupported
  lower reasoning level. Muse Code continues using `MODEL_CODING` with maximum
  reasoning; simulation actors use `MODEL`. The settings model must match `MODEL`.

## What makes execution faster

`RuntimeOptions.max_concurrency` bounds concurrent choices among the actors already
selected by a protocol for a phase. Each receives an independently filtered snapshot
of the same precommit state. Private memory and pending actions are not shared.
The runtime collects choices, validates the batch and commits in declared actor
order, regardless of completion order. Later phases still depend on the committed
previous phase. There is no parallel execution across dependent rounds.

The worker socket server and host subprocess pump both support concurrent requests.
Each reply carries a transport correlation ID, so a fast actor's reply cannot be
delivered to a slower actor. Gateway call-budget reservation is protected by a lock.
Changing only the runtime would have left the relay as a serial bottleneck.

With three independent calls per round, latency can approach the slowest call rather
than the sum of all three, subject to rate limits and resource contention. This is
an architectural expectation, not a measured speedup from a new live run.

The guide and Muse prompt now give soft targets of roughly two minutes for planning,
three for implementation and 10–15 minutes overall on small tasks. They direct the
agent to assemble a minimal coherent plan, consult full source only for a named gap,
retain necessary prototypes, and stop repeating unchanged passing checks. These
targets impose no new turn cap and do not permit weaker tests or speculative results.
Unfamiliar mathematics, unsupported capabilities, dependency changes and provider
latency can exceed the target. A frontier coding model cannot remove those costs by
itself; timings must establish whether the target is met.

## Typed actor customization

`simulation_core.behavior.ActorBehaviorSpec` has native fields `actor_id`, `objective`,
`behavioral_instructions` and `background`. A user-input LLM can populate
`ExperimentRequest.actor_behaviors` through this schema. The coding agent copies
each profile into the matching LLM policy's `behavior` parameter. `JobManifest`
rejects duplicate profiles, unknown/non-LLM bindings and changes to supplied profiles.

The effective instructions combine framework requirements, shared experiment rules
and that actor's private profile. Dynamic observations and owner-only memory are
supplied separately. Shared rules should not specify a conflicting objective.
The framework never adds another actor's profile to this input. Keep profiles out
of public state; public knowledge of roles requires a separate explicit experiment
assumption. Profiles remain in user-facing provenance, which actors do not receive.

Prompted cooperation or opportunism is a tendency, not an enforced strategy. A
requirement such as “always contribute 20 when affordable” needs an explicitly
deterministic `Policy` implementation. The existing policy interface supports both.
Heterogeneous social objectives also change the assumptions behind a selfish Nash
reference; the optional request explicitly requires that distinction in the report.

## Persistence and recovery

Every worker run gets a fresh checkpoint directory under ignored `_runs/`, or an
explicit `checkpoint_dir`. It contains:

- `identity.json`: exact bundle, framework and job identity;
- `checkpoint.json`: canonical committed events and uncommitted completed decisions,
  including pending private-memory updates and model-call records;
- `responses/`: durable request-keyed responses, attempt reservations and usage;
- `timings-<execution-id>.json`: stage, actor and round timings for each invocation.

The host atomically persists snapshots as the worker emits them. Events travel as
append-only deltas to avoid repeatedly transporting the entire event history.
Merging rejects omitted or rewritten commits. Only committed events reconstruct
world state; the pending ledger does not commit a partial round. Policy usage is
restored, so a restart does not reset its call budget.

Response keys include a stable runtime decision ID and the complete request. The
decision ID is transport metadata, not an added actor-visible clock. Identical
observations in different turns therefore remain distinct decisions. Saved responses
can cover the gap between provider completion and checkpoint delivery. Changed
instructions, observations, schemas or model settings cannot reuse an old response.

Resumption is explicit and requires the same bundle/framework/job. An OS file lock
prevents two workers from resuming the same run simultaneously. Persisted responses
are reused without provider calls; failed attempts still consume durable budgets.
Unresolved in-flight reservations are flagged rather than silently queried again.
Exactly-once execution at a remote provider cannot be guaranteed after an ambiguous
network or process failure; retain and reconcile that evidence. Do not delete a
pending marker merely to bypass the uncertainty. Reporting changes should use the
existing offline `report` command and saved result, not resume actor execution.

Components must keep simulation state in `WorldState`, rather than hidden mutable
policy/mechanism/protocol attributes. Custom policies with model-call records must
implement `restore_model_calls`; the parent rejects unsupported restoration rather
than silently forgetting usage. Experiment authors do not implement their own relay
or resume loop.

## Observability

Actor audit entries include duration, response/error metadata, call ID and reuse
status. The host prints a waiting-actor heartbeat every 15 seconds while requests
are in flight. `RunReceipt` includes elapsed time, the recovery directory and
timings for validation, actors, rounds, simulation and reporting. Authoring calls
write `stage-timing-*.json`, including failed calls. Preparation/image-build time
is separate from worker execution time and must be included when assessing the
whole end-to-end target. Provider I/O timeout and worker wall time remain distinct;
there is no competing short local relay socket timeout.

## Commands for a future authorized live run

These commands are examples; preparing these files did not execute them. Use a fresh
namespace. Authoring preserves the existing image/mount exclusions for prior bundles,
host credentials, Git history and trusted tests.

```sh
uv run --no-sync python -m agent_tools --sandbox hypothesis-worker author \
  --request experiment_requests/public_goods_fast.json \
  --actor-settings experiment_requests/public_goods_fast.execution.json \
  --experiment-id public_goods_fast_trial_001
```

For an interrupted sealed run, use its exact saved job and printed checkpoint path:

```sh
uv run --no-sync python -m agent_tools --sandbox hypothesis-worker run BUNDLE \
  --job BUNDLE/job.example.json --live-actors \
  --actor-settings experiment_requests/public_goods_fast.execution.json \
  --checkpoint-dir CHECKPOINT_DIRECTORY --resume
```

`run` requires the matching trusted image to have been prepared. `--live-actors` is
explicit; preview/report never gain a live relay. Actual speed and provider behavior
remain unmeasured until a live experiment is authorized.
