# Repeated public goods: live coding-agent trial

The experiment completed ten rounds with five LLM participants and 50 accepted decisions. The coding agent was Muse Code, powered by `MODEL_CODING` (`muse-spark-1.3`, maximum reasoning); simulation actors used `MODEL` (`muse-spark-1.3-contributor`).

Open the [reviewed, executed notebook](../_runs/public_goods_c547b77e/v5/reviewed/results.ipynb). Its adjacent `result.json` is the saved run; reporting cells do not call actors again. The [report receipt](../_runs/public_goods_c547b77e/v5/reviewed/receipt.json) records zero additional actor calls and no simulation rerun.

## Problem and information

Participants started with zero savings, received 20 each round for rounds 1–5, and received zero thereafter. Everyone knew the ten-round horizon and withdrawal schedule upfront. Contributions were simultaneous and could use any accumulated funds, with no borrowing against the pending pool payout. The pool multiplier was two and proceeds were shared equally. Round payoff was endowment minus own contribution plus two-fifths of total contributions; this payoff accumulated in savings.

The neutral objective was to maximize one's own final balance. Completed contributions, payoffs and balances were public; pending actions were hidden and memory was private to its owner. Publishing the balance ledger was an explicit modeling assumption: those balances were already inferable from the public history.

## What happened

| Rounds | p1–p4 contribution, each | p5 contribution | Meaning |
| --- | ---: | ---: | --- |
| 1 | 20 | 20 | Everyone gave the current endowment. |
| 2 | 20 | 60 | p5 used its entire available balance, including savings. |
| 3–5 | 20 | 20 | Giving returned to 20 each. |
| 6–7 | 20 | 0 | Four participants continued giving from savings after withdrawal. |
| 8–10 | 0 | 0 | Giving stopped despite positive saved balances. |

Each participant contributed 140 across the full run and finished with 240. Total contributions were 700; initial endowments injected 500, and the multiplier generated a further 700 net wealth, giving final group wealth of 1,200. Average contribution fell from 21.6 in endowed rounds to 6.4 after withdrawal.

The reported rationales suggest conditional cooperation followed by endgame defection. p5 noted that others had not matched its early extra contribution and stopped giving at withdrawal. Other actors continued to support a 20-contribution norm through round 7. Several round-8 rationales expected others to keep giving while the actor switched to zero; those simultaneous forecasts were wrong because everyone switched. These are self-reports, not independent causal evidence or hidden reasoning traces. This single trajectory cannot separate withdrawal effects from wealth, expectations and the approaching final round.

The self-interested finite-horizon reference gives zero every round and ends with 100 each, assuming common knowledge of rational, risk-neutral own-wealth maximization. Each contributed unit returns only 0.4 privately. The cooperative full-reinvestment trajectory ends with 39,680 each: each contributed unit adds one net unit to group wealth, and gains can be reinvested. That is an alternate entire history, not an available unilateral deviation from the observed final-round balance or an equilibrium prediction.

## What the coding agent built and reused

The agent authored five Python source files: the public-goods mechanism, contribution schema, arithmetic reference functions, report builder and package exports. It supplied three test files containing 29 tests. It reused the generic simulation core, simultaneous protocol, `llm.v1` policies, private observations/memory, gateway, event recording, registry, worker, verification interfaces and notebook renderer. There was no mathematical solver forced onto this elementary arithmetic problem, and no scripted primary actor actions.

The mechanism declares joint actions, checks configuration and initial state, validates contributions against available wealth, and maintains a reconstructible public ledger. The reference calculations are ordinary reusable functions. Planning prototypes and implementation used one persistent Muse session and workspace, avoiding rediscovery between stages.

The fresh authoring image and context contained only the approved generic toolkit and current request. Historical experiment directories, host home, `.env`, Git data and trusted acceptance tests were absent. All three session volumes were new; mount inspection confirmed only current inputs, workspace and session home. Audit evidence is under `../_authoring/public_goods_c547b77e/`, particularly `isolation.json`, `active_isolation.json` and `context_manifest.json`. These ignored operator files remain local audit artifacts.

## Verification and notebook review

The completed simulation passed Ruff, mypy on all five source files, 30 acceptance/composition tests, and 288 framework regression tests (one skipped). Privacy verification checked 51 recorded model requests against canonical precommit observations: 50 successful decisions and one resolved historical failed attempt. An independent data-only audit checked all contributions, budgets, round payoffs, cumulative balances, withdrawal timing and group-wealth conservation across ten rounds.

The optional generic numeric verifier does not cover this custom economic mechanism. It reported unsupported/unverified rather than claiming proof. Economic confidence here comes from the authored tests and independent arithmetic audit; this is not formal verification.

The prelive notebook review approved the preview. Transport failures interrupted the automated end-to-end authoring workflow before its postlive review; an operator reviewed the completed output. Versions 4 and 5 change only `report.py` among Python sources, correcting theory/causal wording and adding interpretation of the observed trajectory. The v5 report was rendered offline in Docker, passed its 29 frozen authored tests, Ruff, mypy and recorded privacy check, and preserved the original saved result exactly. It has five broad sections and displays the 50 rationales once.

## Failures and recoveries

This was one logical trajectory recovered across several worker executions, not one uninterrupted physical run. No accepted decision was queried again.

1. The original 2,000-token setting truncated both attempts at the first decision. No action committed.
2. At 4,096 tokens, seven decisions succeeded before two 45-second provider timeouts stopped progress.
3. Reusing those seven responses with streaming and a longer provider deadline produced 12 more accepted decisions. Three responses still failed under the token ceiling: one was resolved by a retry; two exhausted the next decision's attempts.
4. After removing explicit generation-token ceilings, ten more responses completed. A separate fixed 75-second relay socket deadline nevertheless abandoned one slow request, even though its provider response completed and was retained.
5. Removing that competing relay deadline and reusing the 29 completed responses plus the resolved failure allowed the remaining 21 decisions to complete. The last worker took about 668 seconds, including validation.

Across these attempts there were 50 completed decision responses and seven failed provider attempts. The reconstruction checks each incoming request against the explicitly supplied current-trial transcript before reuse, preserving original request metadata. Removing the token ceiling was an explicit operator exception to otherwise exact request matching. Unresolved failed tails remained in separate audits; they were not silently turned into accepted actions. Generation settings changed within the trajectory, which limits interpretation of differences over time.

This response-prefix reconstruction is not a durable event checkpoint. The final canonical event log records the completed trajectory, but the framework still needs a first-class resume operation based on committed events plus a pending-decision ledger.

## Toolkit changes and remaining work

The toolkit now omits explicit output-token limits by default, supports optional positive limits, checks scheduled call budgets before execution, supports line charts and intervention markers, formats assumptions as prose, and supports preview/postrun notebook review plus offline report-only rendering. Relay recovery distinguishes reused responses from new provider calls and preserves error metadata. The stale socket deadline was removed; provider and worker deadlines remain. Worker preparation also checks Docker disk headroom before expensive builds.

The next reliability priorities are durable committed-state checkpoints, centralized provider/relay/worker deadline resolution, and concurrent actor requests within simultaneous rounds with correctly correlated replies. The standard gateway's shorter default provider timeout still needs a coherent policy; the recovered run explicitly used a longer streaming timeout. Generation caps are disabled in requests, but providers may impose their own intrinsic limits. Structured data and transport validation remain in place.

Speed also depends on avoiding repeated image builds and excessive authoring deliberation. The initial workflow took about 21 minutes before recovery, including approximately 13 minutes of planning; recovery added substantial sequential actor latency. Persistent sessions and retained prototypes helped, but this trial has not yet established a reliably fast unattended path.

The prior auction's report-only cleanup is available separately at `../_runs/auction_session_bdfb4b4a/v2/cleanup/results.ipynb`; its recorded actor outcomes were unchanged.
