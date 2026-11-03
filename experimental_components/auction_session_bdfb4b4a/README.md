# Fresh auction trial with persistent Muse authoring

The fresh trial completed on its first sealed candidate (`v1`). Muse Code ran with `muse-spark-1.3` at maximum reasoning; the three simulation bidders used `muse-spark-1.3-contributor`. There was one live auction, three accepted actor calls and no actor retries. The generated notebook is retained as produced, including the presentation shortcomings below; no extra polishing stage or live rerun was performed.

[Executed results notebook](../_runs/auction_session_bdfb4b4a/v1/6ff068252870426283ebca799f4d821f/results.ipynb) · [Configuration-only preview](../_authoring/auction_session_bdfb4b4a/preview-1/preview.ipynb) · [Simulation receipt](../_runs/auction_session_bdfb4b4a/v1/6ff068252870426283ebca799f4d821f.json)

## Observed result

| Bidder | Private valuation | Live bid | Payoff |
|---|---:|---:|---:|
| A | 90 | 90 | 25 |
| B | 65 | 65 | 0 |
| C | 40 | 40 | 0 |

A won and paid the second-highest bid, 65. All three recorded actions and the settlement matched the truthful-bidding reference. The original model explanations are recorded once in the notebook's rationale section. Each response used the configured 2,000-token ceiling and was accepted on its first attempt. Reported actor input/output tokens were 697/699, 697/588 and 697/621 respectively.

This is a single fixed valuation profile. Matching the mathematical reference here does not establish a general law of LLM behavior, uniqueness of equilibrium, or correctness for arbitrary auctions. The bidders were told the rules and their objective, not instructed to bid truthfully.

## Isolation and continuity evidence

The authoring inputs were the current user-level auction request, approved toolkit sources/inventory, generic instructions, interface guide/starter and centrally resolved execution settings. Neither past experiment code nor its tests, results, notebooks, review feedback or session home was supplied. The host checked historical experiment identifiers against the approved source payload without reading their artifacts.

Before the first authoring call, all three new volume names were absent. The authoring image probe found no experiment bundles, repository test suite, `.env`, Git history or preexisting session home. An inspection of the running container found exactly three volume mounts: its own inputs, workspace and CLI home. Inputs were read-only. No host checkout or Docker socket was mounted.

Planning and implementation used the same native Muse session UUID, `7428f276-3dd6-4365-aa7b-bb5ddee62069`. Stage metadata records `continuation=false` followed by `continuation=true`. Implementation inspected the retained workspace and compared the frozen tests/configuration against the planning files rather than beginning a fresh broad source-discovery pass. The authoring container and volumes were closed after completion; versioned source and audits remain.

The isolation evidence establishes what this application supplied and mounted. It does not make agent-authored tests independent of agent-authored code. The freshly authored frozen tests were created in this trial's planning stage, not copied from a previous experiment.

## Components authored and reused

The agent reused `LLMPolicy`, simultaneous scheduling, permission-filtered observations, state/event recording, the simulation runner, worker isolation, notebook writers and verification interfaces. It authored four Python package files: auction rules/schemas/truthful reference, a recorded-run checker, preview/final reporting and exports. There are four acceptance-test files. No new general equilibrium solver was needed.

The exported mechanism supports configured actor order and named action/state fields; it does not hardcode the valuation profile into settlement logic. The scientific configuration carries the actors, valuations, rules, permissions and assumptions. The controller resolved actor model, reasoning and budgets before freezing the plan. The actor instructions and initial public state did not disclose rival valuations, uncommitted bids or the truthful reference result.

## Timing and comparison

| Measured phase | This trial | Previous initial trial |
|---|---:|---:|
| Planning | 345.1 s / 33 model calls | 542.7 s / 38 calls |
| Implementation | 313.5 s / 29 calls | 451.0 s / 43 calls |
| Authoring total | 658.6 s / 62 calls | 993.7 s / 81 calls |
| Controller workflow | 748.9 s | 1,125.8 s |

The successful trial took 782.3 seconds (13.0 minutes) including 33.4 seconds of setup, before resource teardown. Initial authoring was about 34% faster, with about 23% fewer model calls. Planning plus implementation used 77 tool operations versus 118 previously. Implementation's initial inspection consisted of six operations instead of the previous broad source-reading pass.

The previous notebook also required a later 31-call presentation revision. This trial had no such revision, but its prose is less polished in the ways noted below. These are not controlled causal measurements: the starter, guide, persistent context, single live execution, execution settings and prompt changes were introduced together, and model generation varies.

Provider-reported coding usage was 7,129,030 input tokens (6,961,773 cached), 65,964 output tokens and 35,790 reasoning tokens. Cache/reasoning numbers are categories, not additional tokens to sum on top of those totals. Retaining history did not eliminate long prompts: implementation alone reported about 4.3 million input tokens across 29 calls, mostly cached.

The user's whole launch sequence was longer than 13 minutes. From the first launch attempt to successful simulation completion was approximately 24 minutes, before this review. An initial driver argument error occurred before any model call. One image build then exhausted the worker's 10 GB Docker disk, and another attempt exposed a session-input ownership bug before reaching Muse. Unused build cache and obsolete toolkit image caches were removed, preserving experiment files and recovering roughly 3.3 GB. The ownership helper was fixed to leave a workspace already owned by UID 10001 accessible without requiring root chmod privileges. A Docker lifecycle test matching that production ownership passed before the successful fresh trial. None of these failed setup attempts called the provider or generated an earlier auction solution accessible to this agent.

## Verification

- Ruff passed; mypy passed for all four generated source files.
- All 18 agent-authored acceptance tests plus the framework offline composition test passed (19 total), including ties, legal overbidding/negative payoff, illegal negative/nonfinite bids, unsupported parameters, benchmark examples, sampled dominance cases, checker tampering detection, offline privacy and notebook structure.
- All 279 toolkit regression tests passed, with one skipped.
- Composition and declared-test coverage passed.
- The offline preview kernel executed before live bidding, showed a calculated theoretical reference, and explicitly left observed LLM performance and rationales pending.
- The final notebook's four code cells executed, displaying the result table, two plots and rationales. They load the saved artifact and do not call models.
- The trusted observation checker verified all three LLM requests against canonical precommit actor observations, including identity, public/private facts and memory.
- The agent-authored auction checker verified allocation, payment, utilities, legality and recorded history. Structured numeric optimization checks were explicitly unsupported/unverified and non-required for this piecewise auction; they were not silently claimed to have verified it.

## Remaining issues and next priorities

1. **Editorial compliance is still incomplete.** The interpretation repeats every bid, valuation and payoff already in the table. Assumptions append raw configuration strings and a Python-style list such as `['valuation']`. The structure is right, but the user's preference for interpretation over repetition and ordinary-text assumptions needs stronger content review. Structural acceptance alone did not enforce it.
2. **Guide use improved but did not prevent rummaging.** Planning still read registry, planning, assembly and runtime internals. Improve the guide's coverage of the exact authoring contract and known validation requirements, rather than assuming an instruction to avoid those files is sufficient.
3. **Important capability declarations are missing.** The mechanism requires a complete joint action profile but does not set `requires_joint_actions=True`. This actual simultaneous experiment works; a future incompatible sequential composition might fail later than intended. The guide should explain significant class-level capability flags, not just list methods.
4. **Preflight coverage needs strengthening.** Private valuation validity is checked during clearing rather than fully during configuration/state preflight. These valid inputs work, but malformed future inputs could consume actor calls before failing. Not every configurable field is materially exercised; `rules_field` is declared but unused by the implementation.
5. **Mathematical evidence remains correlated.** The truthful reference shares `_ranked` with settlement. The custom check has a separate function but duplicates the same ranking logic. Hand-derived cases and tampering tests are useful evidence; sampled dominance tests do not prove the theorem over every real bid profile.
6. **Infrastructure caused avoidable latency.** Disk headroom should be checked before image builds. Production image ownership belongs in lifecycle integration coverage. Framework changes should not require repeating expensive CLI/OS dependency installation. These issues dominated the failed startup attempts, not model inference.
7. **Completion needs a substantive content gate.** The controller correctly stopped after passing checks and a report, but a structural pass is not the same as satisfying editorial requirements. A short review before declaring authoring complete should identify a named defect and request a bounded fix within the retained session, without another live simulation. No turn cap is needed.

Apart from the necessary pre-launch ownership fix, no architectural or notebook improvements were implemented after the successful experiment. Audits and raw traces are under `experimental_components/_authoring/auction_session_bdfb4b4a/`; runtime exports remain ignored artifacts, while `v1/` and this report retain the experiment source for version control.

## User-requested cleanup after this review

A new sealed `v2` removes the repeated result enumeration from interpretation,
uses human assumption rationales without raw configuration dumps, declares joint
batch requirements, and validates valuation facts/public-rule presence before
execution. It passed the original frozen source checks/tests and re-rendered the
same saved result offline. No further bidder calls occurred.

[Corrected notebook](../_runs/auction_session_bdfb4b4a/v2/cleanup/results.ipynb).
The original `v1` and its simulation receipt remain unchanged.
