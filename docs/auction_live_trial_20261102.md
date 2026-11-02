# Auction coding-agent trial — 2 November 2026

**The Muse Code trial completed successfully on its first submitted implementation,
`auction_muse_20261102/v1`.** It generated the custom auction code and tests, ran
actual LLM bidders, and produced an executed notebook with the theoretical
comparison. Independent review then exposed four limitations described below.
The completed bundle has not been repaired or changed after the experiment.

- [Executed notebook](../experimental_components/_runs/auction_muse_20261102/v1/dc51c9f6ee47418688ab60c2e6ff85b1/results.ipynb)
- [Saved experiment result](../experimental_components/_runs/auction_muse_20261102/v1/dc51c9f6ee47418688ab60c2e6ff85b1/result.json)
- [Validation receipt](../experimental_components/_runs/auction_muse_20261102/v1/dc51c9f6ee47418688ab60c2e6ff85b1.json)
- [Versioned agent-written source](../experimental_components/auction_muse_20261102/v1/experiment_extension/auction.py)
- [Resolved request/configuration](../experimental_components/auction_muse_20261102/v1/job.example.json)
- [Independent probe results](../experimental_components/_authoring/auction_muse_20261102/independent_review.json)

Receipts, notebook/result pairs and raw model logs are retained locally under the
existing ignored, restricted audit/output directories. The source bundle and this
report can be versioned. An ignored output is retained locally, not deleted.

## Experiment and actual result

The operator acted as the user and supplied a textbook sealed-bid second-price
auction for one indivisible item. Three bidders have private values 90, 65 and 40.
There is one simultaneous round, no reserve and no budget constraints. Bids must
be finite and nonnegative; overbidding, underbidding and negative realized utility
are legal. Highest bid wins, pays the second-highest actual submitted bid, and
highest ties use the configured bidder order. Losers pay zero and earn zero.
The assumptions are private values and risk-neutral quasi-linear utility.

| Bidder | Private value | Actual LLM bid | Truthful-reference bid | Actual utility | Reference utility |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 90 | 90 | 90 | 25 | 25 |
| B | 65 | 65 | 65 | 0 | 0 |
| C | 40 | 40 | 40 | 0 | 0 |

**A won and paid 65.** All bid and utility differences from the truthful profile
were zero. This was not hardcoded action selection: each committed bid came from
an accepted live `muse-spark-1.3-contributor` response, with its provider request ID
and concise rationale recorded. The actor prompts explained the rules and asked
for a preferred bid; they did not instruct truthful bidding or disclose the
benchmark, other valuations or other uncommitted bids.

For example, A's recorded rationale says: “My private valuation is 90.” It then
explains that the price is the second-highest bid and selects its own value. B and
C independently gave the same second-price reasoning for their own values.
These are recorded decision explanations, not exposed private chain of thought.

The theoretical comparison is a **pure post-commitment truthful-reference
function**, not a new numerical optimizer, a Nash enumeration, or a replacement
for the actor policies. Under the stated assumptions, truthfulness is weakly
dominant; it is not a unique-equilibrium claim. The final request explicitly
allowed this smaller reference route and `benchmark=null`. Therefore the result
has no framework `BenchmarkReport`; the notebook calculates and presents the
truthful comparison separately. This distinction should be preserved when
comparing this notebook with the earlier Nash-benchmark notebooks.

## What the coding agent received and reused

The coding model was `MODEL_CODING=muse-spark-1.3`, reasoning effort **max**, through
Muse Code **1.4.14 / 1.4.14-R7309.1**, with Contributor mode off. Actors remained on
`MODEL=muse-spark-1.3-contributor` through the separate host actor gateway. Both
roles used the existing API key as authorized; `.env` was not modified.

The CLI received the fresh request, general instructions, native response schema,
component inventory and read access to the installed toolkit. It inspected
interfaces and approved examples on demand. Its container had no past allocation
bundles, past trial results, host home, `.env`, Git history, controller conversation,
old Muse sessions or framework regression-fixture directory. It could see approved
toolkit examples, including the payoff-matrix example; that is library context,
not access to the hidden allocation trials. Web tools and foreign personal context
were disabled. No subagents were used.

| Responsibility | Reused toolkit capability |
| --- | --- |
| Bidding decisions and per-action explanations | `llm.v1` / `LLMPolicy` |
| One action per bidder and sealed joint commitment | `simultaneous.v1`, trusted runtime |
| Public/private observation boundaries and own memory | `WorldState`, observation permissions |
| State transitions and canonical records | `Mechanism`, runtime, events and replay |
| Typed requests, configuration and source artifacts | Existing Pydantic/native authoring contracts |
| Gap analysis, schema/binding checks and test freeze | Existing controller/static planning review |
| Versioning, hashing, preflight and validation gates | Existing experimental bundle/worker machinery |
| Reporting inputs | `JobResult`, `simulation_core.reporting.result_rows` |

The CLI used `read_file`, `bash`, `write_file`, `edit_file` and `write_todos`.
It did not have a host shell or the host Docker socket. Its local tool commands
ran in its authoring container; the separate worker made the actual acceptance
and final simulation runs.

## What was created from scratch, and by whom

The external coding agent wrote the following in the versioned experiment bundle:

- `BidPayload`: finite, nonnegative scalar bid schema.
- `AuctionParameters`: rule/configuration schema and field-name conventions.
- `SecondPriceMechanism`: joint bid validation, settlement, state/history updates
  and state checks, implementing the existing `Mechanism` parent.
- `truthful_reference` / `TruthfulReference`: theoretical reference helper/data.
- `AuctionSettlementCheck`: experiment-specific `VerificationCheck` implementation.
- `generate_results_notebook`: notebook generator with actual/reference plots,
  recorded rationales, assumptions and limitations.
- Five test files, including reusable test fixtures; 19 named test functions.
- The native experiment configuration, gap analysis, component declarations and
  24 recorded assumptions/conventions. Four components are registered through
  `CustomComponentSpec`; the checker and report generator use their dedicated
  manifest entrypoints.

The operator wrote the **general infrastructure**, not the auction implementation:

- A credential-free actor relay for the offline simulation worker, missing before
  the trial. Host credentials remain outside that worker.
- The checksum-pinned Muse Docker installation and CLI gateway/entrypoint.
- File-to-Pydantic response assembly, so the CLI can write ordinary Python files
  rather than generate one enormous code-containing JSON answer.
- Default backend selection, the generic Muse prompt, tests and usage documentation.
- The illustrative user request and independent post-run probes.

No auction logic was manually repaired by the operator. Mechanical normalization
used the existing Ruff formatter/import sorting and retained its audit hashes.
The operator retained one unapproved data-only snapshot while implementation was
in progress, to avoid losing source on a transport failure. It was not used to
replace the CLI response or supplied back to the model.

## Execution and checks

The plan passed controller review with **zero findings**, then its tests,
configuration and exports were frozen. Muse completed implementation in the next
stage. The first submitted bundle, v1, passed every existing required gate:

| Gate | Result |
| --- | --- |
| Ruff | Passed |
| Mypy | Passed for both generated source files |
| Acceptance | 20 passed, including the trusted framework integration |
| Toolkit regressions in Docker | 252 passed, 1 skipped |
| Declared acceptance coverage | All declared tests executed |
| Registry composition/preflight | Passed |
| Required auction settlement/privacy check | Reported verified |
| Notebook | Both code cells executed; no execution errors; comparison plot inspected |

The framework's generic numeric-expression checks correctly stayed optional and
reported unverified/unsupported: this auction was not forced into the earlier
continuous numeric problem language. Its applicable required check was the custom
auction checker. This is scoped verification, not proof that every possible
configuration or checker is correct.

There were **six live actor calls**: three in framework acceptance integration and
three in the final run. Both auctions produced bids 90/65/40. The final artifact
contains only its own three decisions. These two executions are validation plus
one demonstration, not a meaningful statistical sample of bidding behaviour.
All saved actor inputs were inspected: each exposed only `rules` and that bidder's
own `valuation` and memory. No bids were visible before commitment.

The notebook reads its sibling `result.json` and makes no new model or simulation
calls. It shows bids versus private values and actual versus reference utilities,
with rationale and assumption text. Its executed plot was extracted and visually
inspected. No notebook cells or generated experiment modules were executed on the
host during review.

The final bundle seal remains unchanged after all independent probes:

`596c1d51694e960fa6fb4ebae7fcc4a116203d4d490f63822be693e254d3d496`

The exact validation image is recorded in the receipt:
`sha256:6deb03d803ba7c7c224ea3089f7db48221e98b2ebcc14eb11d2d3d424b5671d0`.

## Independent checks and concrete defects

A separate disposable, offline Docker process ran externally prepared checks.
Their cases were not supplied to the coding agent, and they made **no model calls**.
The agent's source bundle, actual result and sealed tests were not modified.
Fault injection below changed only a module binding in that disposable process.

Ten settlement cases passed: different winners, legal negative utility, all-zero
bids, two highest-tie patterns, fractional values, changed valuations, and arbitrary
new IDs with **two and four bidders**. The actual validators also rejected negative,
boolean, string, NaN and infinite bids. These checks support the claim that the
mechanism generalizes beyond the three illustrative values and bidder names.

Four additional probes exposed limitations that the baseline gates missed:

### 1. Privacy-checker identity substitution — fix before relying on its guarantee

The probe changed a recorded call attributed to A so its observation claimed to
be B and contained B's private valuation. The custom checker still returned
`verified`. It trusts the observation's actor ID instead of requiring it to equal
the call's actor ID, then compares against that other actor's permissions/facts.

The actual saved calls are correctly isolated. This probe demonstrates a **false
positive in the checker**, not an observed leak in the successful auction.
A reusable trusted check should bind call actor, request actor, observation actor,
authorized state and committed action, rather than trusting a supplied identity.

### 2. Settlement verification is a consistency check, not an independent oracle

The mechanism, truthful-reference helper and custom checker share
`settle_second_price`. The probe replaced that function locally with a wrong
first-price settlement. The mechanism charged A **90 rather than 65**, and the
checker still returned `verified`, because it used the same wrong function.

The existing fixed-example acceptance tests would catch this particular first-price
mutation, and the independent settlement cases passed the real implementation.
Nevertheless, the generated checker's claim of independent recomputation is too
strong. Use an independently implemented oracle or externally grounded cases and
fault-injection tests when an independent guarantee is required. Reuse of a rule
helper is useful for consistency, but cannot establish its own correctness.

### 3. A declared field-name variation breaks the notebook

`valuation_fact="value"` is accepted, and the mechanism successfully runs with
that private-state key. The notebook generator's Python preparation respects it,
but an emitted notebook cell hardcodes `facts["valuation"]`. Executing that
notebook raises `KeyError: 'valuation'`.

The original notebook is correct for the supplied configuration. To support the
advertised variation, its cells should use the configured key or consume prepared
comparison data. The notebook also duplicates auction reference calculations
inside a code cell rather than delegating all of them to the tested external
reference helper; that duplication invites drift.

### 4. An accepted configuration option has no effect

`allow_above_valuation=False` passes the generated parameter/config validation,
but the mechanism still accepts overbidding and can give the winner negative
utility. The flag is unused. The requested experiment explicitly permits
strategically poor bids, so the present result is correct; the schema's optional
false value is misleading. For this mechanism version, reject unsupported settings
or make the supported convention a constant. Do not silently invent a restriction
that contradicts the requested auction.

## What the run revealed about agent behaviour and guardrails

The CLI independently corrected strict Python-list/tuple Pydantic errors in its
draft builder, import sorting, an incorrect lint path, and implementation lint/type
findings. It recovered from provider stream truncations and eventually submitted
valid native artifacts. The controller did not rewrite its scientific assertions,
weaken frozen tests, substitute scripted bidders, or accept its claimed success
without a worker receipt.

The read-only installed scaffold and artifact path validation kept extensions in
the experiment namespace. Parent interfaces were sufficient: no simulation-core
change was required for the auction. Current mechanisms, generic policies and
simultaneous runtime therefore compose into this unfamiliar experiment.

The guardrails did **not** make generated verification automatically reliable.
The independent probes above are important evidence: a required checker can run
successfully and still miss bugs outside its assertions. The toolkit already says
an agent-authored checker is not automatically independent; this trial makes the
practical limit concrete.

## Workload, observability and remaining operational issues

The successful fresh auction had **two controller authoring stages** and one
submitted implementation version. Native CLI usage reports:

| Stage | Provider calls | Completed / failed | Input tokens | Cached input tokens | Output tokens | Reasoning tokens |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| Plan and tests | 69 | 67 / 2 | 7,522,699 | 7,357,730 | 64,153 | 36,736 |
| Implementation | 43 | 42 / 1 | 3,877,345 | 3,752,217 | 44,149 | 29,199 |
| Total | 112 | 109 / 3 | 11,400,044 | 11,109,947 | 108,302 | 65,935 |

These are native CLI-reported aggregates, not a complete billing ledger for failed
calls. Reasoning tokens are a subset of output tokens. The controller measured
1,534.9 seconds after initial validator preparation, approximately **25.6 minutes**.
The six actor calls separately recorded 4,710 input and 4,043 output tokens; the
final three accounted for 2,355 input and 2,294 output tokens. Authentication smoke
checks and earlier abandoned direct-API attempts are outside these auction totals.

There were 149 recorded coding-tool results: 61 file reads, 56 shell commands,
12 file writes, 16 edits and four todo updates. This is far too much exploration
and bookkeeping for a small auction, even with most input cached. The useful
immediate improvements to consider before repeated trials are:

1. Address the four concrete defects above and add the independent counterexamples
   as applicable trusted checks in a future version; leave this completed v1 intact.
2. Show meaningful tool descriptions, elapsed time, retries and stage transitions.
   The current console repeats many low-level event names, obscuring progress.
3. Propagate native `run.usage` into authoring metrics. The generic bridge response
   currently leaves token fields at zero; those mean unavailable, not free usage.
   Controller stage counts must not be confused with the CLI's provider-call count.
4. Automatically retain partial CLI workspace artifacts on terminal failure. This
   run needed an operator-created unapproved snapshot; cleanup otherwise removes
   a failed stage's workspace even when useful source files exist.
5. Reduce repeated source exploration and restating frozen metadata. Consider
   preserving this trial's own context between stages while keeping the frozen
   inputs read-only and excluding every other experiment. A fixed turn cap is
   not needed to expose and improve this overhead.

No architecture optimization or repair of the generated experiment has been
implemented after this run. Following the user's strategy, the next substantive
trial should exercise different interaction rules, for example a first-price
auction or a public-goods game, after the most consequential verification defects
are addressed. One completed second-price auction demonstrates the path; it does
not establish broad generalization.

## Earlier attempts and CLI installation

Before the user changed tactics, direct API authoring never produced a complete
plan:

| Attempt | Settings | Outcome |
| --- | --- | --- |
| `auction_live_20261102` | 32,000 output tokens, 180-second timeout, full context | Transport error |
| `auction_retry_20261102` | 32,000 tokens, 600-second timeout | `provider_incomplete_max_output_tokens` |
| `auction_extended_20261102` | 96,000 tokens, 900-second host timeout | Upstream HTTP 504 |
| `auction_compact_20261102` | 16 rather than 30 public source files, 64,000 tokens | HTTP 504 after 597.2 seconds |

The full task was about 190 KB plus an 18 KB output schema. The compact task was
about 109 KB. Meta documents that reasoning counts against the output budget and
that long non-streaming generations are subject to a server time limit; see
[reasoning](https://dev.meta.ai/docs/reasoning) and
[Responses streaming](https://dev.meta.ai/docs/protocols/responses).
Streaming support was added to the optional API transport before the tactical
switch; no further full auction was attempted through that backend.

CLI setup encountered and corrected an unsuitable BuildKit base-image reference,
copied directory permissions, HTTP package repository access, Meta download/API
host policy, and an incompatible settings-file format. The pinned binary's actual
headless help revealed `--api-key-stdin`; the implementation uses it instead of
credential environment variables. A live authentication/tool smoke then passed
in 42.6 seconds including preparation, using two provider calls. It was not an
auction. Before the live auction, 250 offline tests passed with three skips; the
separate in-Docker regression gate subsequently passed 252 with one skip.

The active generic prompt is [muse_coding_agent.md](../prompts/muse_coding_agent.md).
The default coding factory now selects Muse Code. The old direct-API prompt and
backend remain explicit alternatives, not the path used for this successful run.
See [CLI setup and boundaries](muse_code_worker.md) for the runnable command and
full authentication/isolation description.

The CLI used `--yolo` **inside the disposable authoring container**; Docker remained
the enforced boundary. It ran non-root with a read-only root, bounded writable
workspace/home, dropped capabilities and no Docker socket or host directory mount.
Only this sandbox received added HTTPS allowances for Meta's official download
and model hosts. The validation/simulation worker remained `network=none` with
no key, using the host relay for its actors. API-key authentication still incurs
provider API usage; the change is who manages the coding-agent tool loop.
