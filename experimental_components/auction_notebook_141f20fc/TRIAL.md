# Fresh auction trial: notebook clarity and observability

This trial tests whether a fresh external coding agent can build a live LLM auction simulation using the approved toolkit, produce an explanatory notebook, and leave an auditable record. It is one small demonstration, not evidence of reliable generalisation across arbitrary experiments.

## Isolation and what “frozen tests” means

The coding agent received a fresh user request, generic instructions, approved toolkit sources/inventory and execution capabilities. The authoring image was probed for absence of previous experiment bundles, repository tests, Git history and `.env`. Previous auction and allocation implementations, outputs, notebooks and trial reports were not supplied. Credentials were delivered separately to the CLI, not mounted as a file. The runtime authoring workspace is fresh for each stage.

The **new agent wrote this trial's acceptance tests in its planning stage**. The controller then froze those files before implementation and supplied them read-only to subsequent stages of the same trial. “Current-trial frozen tests” does not mean tests copied from a previous experiment. Passing the agent's own tests is not independent proof: planning and implementation can share a mistake. Separate toolkit regression tests run in the validation container, outside the author's accessible image, and trusted generic checks inspect recorded LLM observations. The custom economic checker is also agent-authored; separate source code does not make it an independently trusted oracle.

The report-only continuation receives this trial's own code/tests and generic presentation feedback. It does not receive recorded bids, rationales, outputs, or any earlier experiment artifacts. Its notebook is rendered offline against the unchanged saved simulation result.

## Problem and outcome

Three private-value bidders submit simultaneous sealed bids for one item. Highest bid wins and pays the second-highest bid; ties use configured actor order. Each bidder sees its own valuation and public auction rules, not rival private valuations. The primary actors use `muse-spark-1.3-contributor`. The coding agent uses `muse-spark-1.3` at maximum reasoning through the pinned Muse headless CLI.

| Bidder | Private valuation | Recorded live bid | Payoff |
|---|---:|---:|---:|
| A | 90 | 90 | 25 |
| B | 65 | 65 | 0 |
| C | 40 | 40 | 0 |

A wins and pays 65. Recorded bids match the truthful-bidding reference in this run. The theoretical comparison is a separately calculated truthful strategy profile under the stated assumptions, not a new equilibrium solver or an enumeration of every equilibrium. One successful profile cannot establish that these LLMs always bid truthfully or that the whole implementation is mathematically correct.

## What the toolkit supplied and what was newly authored

The toolkit supplied simulation state/events, simultaneous protocol, action validation, `LLMPolicy`, actor API relay and traces, registry/composition checks, isolated Docker execution, the five-section notebook writer, reporting data models and shared display helpers. It also supplied authoring schemas, bundle sealing, frozen-test staging, lint/type checks, regression execution and verification interfaces.

The coding agent authored six Python modules: package exports, bid/config schemas, a second-price auction mechanism, a truthful-profile reference, a recorded-settlement checker, and a report generator. It authored three acceptance-test files and the experiment configuration/assumptions. Domain calculations live in these modules; notebook cells call external helpers. Tests use scripted/fake policies for deterministic rule checking, while the final primary simulation uses live actors. The operator supplied the user-level scenario and reviewed prose; the operator did not write the auction mechanism or observed bids.

## Changes delivered before the trial

- Shared notebook reporting supports background/rationale, execution/results/reference interpretation, a single rationale section, plain-language assumptions and limitations. It binds report metadata to the authoritative result hash and validates layout before and after offline execution.
- CLI native events and progress are saved incrementally. Progress includes tool descriptions, elapsed time, provider retries and periodic heartbeats. Usage summaries aggregate per native run without repeatedly counting cumulative events.
- Failed CLI stages retain failure metadata and a bounded, explicitly unapproved source snapshot for diagnosis. No generated code is imported on the host.
- Current-trial frozen tests are staged read-only, and repair stages receive their own editable implementation files instead of reconstructing them from prose.
- A trusted check binds builtin LLM requests to canonical actor observations, including actor identity, public state, allowed private state and memory. It compares all recorded attempts and requires a successful accepted decision for each committed LLM action.
- Offline worker stages report progress for lint, types, acceptance, regressions, simulation and notebook execution. Validation/report containers have no credentials or network.

## Validation and effort

The actual simulation bundle passed Ruff, mypy (six source files), 21 acceptance tests, 264 toolkit regression tests (one skipped), declared-test checks and composition preflight. The notebook's four code cells executed in the isolated worker. The observation check verified four final-run requests: three accepted decisions and one rejected/retried response. Custom settlement checking also passed. These checks establish the recorded evidence within their stated scope; they do not prove all auction variants or prose semantics.

Initial planning took approximately 543 seconds / 38 model calls; implementation approximately 451 seconds / 43 calls. Controller time through validation and simulation was 1,125.8 seconds (18.8 minutes). Initial authoring used 7,860,464 reported input tokens (7,560,159 cached), 97,459 output tokens and 63,644 reasoning tokens; reasoning/cache fields are provider categories and should not be added to those totals as separate tokens. Report refinement is measured separately.

Across live acceptance execution and the final simulation there were eight actor API attempts: six accepted decisions and two output-limit failures. One retry occurred during acceptance and one in the final simulation. This is not eight committed auction actions: the final auction has exactly three. The author left the actor output limit at the default 1,000 despite a preferred 2,000-token capability hint, which contributed to avoidable retries.

## What still needs attention

1. Structural notebook checks cannot judge explanation quality. Human review caught repeated table values in prose and an imprecise distinction between matching actions and matching outcomes. The report-only continuation addresses those presentation issues without rerunning actors.
2. Actor configuration hints need stronger resolution: the preferred output budget was available but not adopted. The system should distinguish defaults, preferences and enforced limits clearly.
3. Actor error logs preserve failure categories but do not retain complete provider usage for failed responses. Cost totals can therefore undercount failed attempts.
4. Authoring remains expensive and read-heavy: 81 model calls before presentation refinement. Better summaries and less repeated file inspection remain opportunities, but no fixed turn cap was reintroduced.
5. Agent-authored tests and custom economic checks remain correlated evidence. Broader parameter variation, counterexamples and an independently maintained economic reference would strengthen validation. This trial does not establish that all custom tools are correct.
6. This scenario does not test reserves, repeated auctions, correlated valuations, risk aversion, budgets or learning. The mechanism's declared scope is the configured one-item, no-reserve, private-value auction.

Raw audit logs, image identifiers, input isolation probe and validation receipt are under `experimental_components/_authoring/auction_notebook_141f20fc/` (ignored runtime artifacts). The original sealed simulation is version `v1`; the explanatory report revision is version `v2` and is not a second simulation run.

## Report-only continuation and operator tooling

A separate presentation-only coding stage used 31 provider calls over 244.5 seconds. It changed only `experiment_extension/report.py`; the frozen tests, configuration, mechanism, reference and checker stayed byte-identical (bundle metadata/seals change with version). It received no observed results. The revision distinguishes matching actions from matching settlement outcomes, explains domain terms and gain/loss, avoids repeating all table values in prose and derives participant counts from configuration.

The operator's one-off offline renderer needed corrections before execution: strict saved JSON requires Pydantic's JSON validator; staging permissions must be set before VM copy; read-only containers need writable temporary caches. These were renderer setup failures, not extra simulations or model decisions. The original receipt's exact Docker image was no longer available; rendering uses the retained image under the same framework-digest tag and records the actual rendering image separately. The original image receipt is preserved. Exact image retention remains an operational improvement to make.

The final report-only container passed Ruff, mypy and all 20 frozen unit tests, rechecked recorded-observation privacy and settlement, and executed all four reporting cells. It intentionally did not execute the extra live-composition acceptance case again. The exported `result.json` is identical as parsed data to the original simulation result. No additional actor API calls were made. Total coding-model calls including presentation refinement: 112; the initial 81-call build and 31-call presentation pass are reported separately above.

[Open the revised executed notebook](../_runs/auction_notebook_141f20fc/v2/report-daf8141b7d1b42f38a506e9e789f18a5/results.ipynb). Its sibling `report_revision.json` records checks, source/result provenance, the actual image and zero actor calls. Generated outputs remain ignored runtime artifacts, while both versioned experiment source bundles and this report remain available for version control.

A final wording limitation remains: the notebook uses “knows only their own valuation” to describe both privacy and independence. Those are distinct mathematical concepts, and independence is not needed for ex-post truthful-bidding dominance in this private-value mechanism. This does not change the recorded settlement, but is another example of prose semantics lying outside structural checks. Further polishing should avoid adding unnecessary theorem assumptions or equating information access with statistical independence.
