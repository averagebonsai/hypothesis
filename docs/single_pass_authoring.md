# Single-pass authoring

The default external-agent workflow authors a complete candidate in one continuous
Muse Code pass: short gap analysis, configuration, implementation, tests and notebook
generators. It does not ask for a throwaway prototype followed by a separate
implementation submission. Repairs and notebook review retain the same session.

`AuthoredCandidate` contains a `CodingPlan` and an `Implementation`.
`CandidateResponse` contains either that candidate or a terminal `ReviewRequest`.
The direct-API backend returns these native objects explicitly; the filesystem
backend collects them from ordinary workspace files. Neither uses JSON-encoded
configuration fields.

## Workflow and boundaries

1. Record the immutable user request in `frozen_request.json`.
2. Author the complete candidate, using approved components and extending only gaps.
3. Run `author-check` in the authoring container. Repair named failures while
   retaining unrelated passing work.
4. Review the offline notebook preview. It explains rules, theory, assumptions and
   limitations; it does not predict or interpret unobserved actor performance.
5. Seal a versioned candidate and record `candidate-freeze-N.json` before permitting
   live execution. Independent worker checks still run against the sealed bytes.
6. Run one primary trajectory. After any actor calls or recorded result, failures
   stop automatic execution. Reporting repairs render the saved result offline.

Prelive candidate revisions may correct code, tests and metadata together, with
versioned evidence and an unchanged user request. Supplied typed inputs and actor
profiles remain checked. Tests must retain independently grounded expectations;
changing a test to conceal a violation of the request is not an authorized repair.
Agent-authored tests are correlated evidence, not independent proof. Trusted
framework checks and applicable independent verification remain separate.

Technical preview failures may repair the affected prelive dependency. Preview
editorial repairs use `repair_scope=report_only`: configuration, tests and
all source except the declared reporting module must remain byte-identical. A
rejected revision cannot replace the previously approved scientific baseline.
Postlive report repair retains the existing strict source guard.

## Runnable starters

```sh
uv run --no-sync python -m agent_tools starter /tmp/my-authoring-workspace \
  --experiment-id example
uv run --no-sync python -m agent_tools starter /tmp/my-tool-workspace \
  --experiment-id example_tool --kind tool
```

Muse receives a starter generated for its experiment namespace under
`/inputs/starter`. The simulation example demonstrates a bounded numeric signal,
typed legality checks, state transitions, hand-derived tests, a mathematical point
reference and preview/final notebook writers. The direct-tool example demonstrates
a typed callable and ordinary tests without simulation scaffolding.

These are synthetic teaching examples, not prior experiment implementations or
LLM results. Their deterministic actors, scalar payloads and objective must be
adapted to the actual request. Requested LLM simulations must use the requested
policies and private actor profiles. Copy only needed files and reuse approved
mechanisms when their rules already match.

## One completion command

Inside the authoring container:

```sh
author-check
author-check --only types tests
author-check --no-cache
```

`python -m extension_worker.author_check` is equivalent. Host execution is rejected
before any authored code can be imported or run. The command:

- normalizes import order and formatting, then checks lint;
- validates native configuration, bindings, metadata and test declarations;
- runs mypy and the relevant authored test suite;
- checks registry composition and initial-state compatibility;
- executes the offline notebook preview for simulations;
- writes `response.json` only when all sections pass for their current inputs.

Failures are grouped by section in `.author-check/report.json`, with measured wall
times and diagnostics. `--only` reruns selected failures and reuses unchanged
passing sections; it cannot report readiness while another section is unverified.
Source, configuration, test and toolkit changes invalidate affected cached checks.
A check that rewrites its own checked inputs fails rather than blessing stale
results. No live actor relay is opened. The final controller worker remains the
authoritative validation boundary; the local cache is only a development aid.

Composition and preview run in separate subprocesses inside the container to avoid
stale experimental imports. Direct tools validate signature and typed arguments;
their computations are exercised by tests rather than an invented actor loop.

## Mechanical metadata

The collector discovers source files, test files and test function names. Bundle
namespace and version default to the controller's experiment ID and `v1`.
`component_id(experiment_id, kind, symbol_name)` generates stable namespaced IDs.
Existing explicit IDs and acceptance declarations remain supported.

A draft component can group tests by file:

```json
{
  "kind": "mechanism",
  "symbol": "experiment_extension.component:CustomMechanism",
  "gap_id": "rules",
  "purpose": "Implement the missing rules",
  "test_groups": [{
    "file": "tests/test_rules.py",
    "category": "functional",
    "expected": "The specified settlement and rejection cases hold",
    "reference": "Separately hand-derived examples from the problem statement"
  }]
}
```

The collector fills test names from that file. The author still supplies meaningful
expectations, reference grounding, rules, assumptions and mathematical guarantees.
No scientific expectation is inferred from a filename.

## Timing and repair evidence

- `workflow-progress.jsonl`: timestamped controller transitions.
- `stage-timing-N.json`: coding-stage elapsed time, including failures.
- Muse `activity.json`: inspection, writing, checks and repair counts, plus observed
  intervals before tool completions. These intervals include model deliberation and
  event delivery; they are not exact tool execution durations.
- `.author-check/report.json` and `history.jsonl`: exact check wall times, cache reuse
  and changed source hashes between invocations. Each invocation has a stable ID.
  The native adapter exports the latest report and bounded history summaries into
  each stage's host `author-check.json` before workspace cleanup; deduplicate these
  cumulative snapshots by invocation ID when aggregating.
- `candidate-review-N.json`: changed file paths, repair scope and static findings.

A five-minute offline-validated candidate is a target for small supported tasks.
No model turn cap, output-token ceiling or lower coding reasoning level was added.
No new LLM experiment was run to measure this target. Offline Docker tests with
networking disabled verified both starters and cache reuse; the simulation starter's
checks took about nine seconds, with an unchanged cached rerun below 0.1 seconds.
Those measurements describe the checker, not LLM authoring speed.

## Compatibility

`author --legacy-staged` explicitly selects the previous plan-then-implementation
workflow. `CodingAgent(..., combined_authoring=False)` does the same for callers.
Legacy methods and saved bundles remain supported. The standard CLI and
`CodingAgent` now default to complete-candidate authoring.
