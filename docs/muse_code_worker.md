# Muse Code headless coding worker

Authoring now defaults to a complete candidate in one pass, with executable starters
and `author-check`. See [single-pass authoring](single_pass_authoring.md). Use
`--legacy-staged` only for the older separate planning/implementation contract.

The default coding backend is now **Muse Code**, installed in its own Docker
image. `CodingAgent.from_environment(..., sandbox="hypothesis-worker")` selects
it; the former direct Responses API backend is available only with
`backend="api"`. Simulation actors retain their separate `MODEL` setting.

The version is pinned in `docker/muse-release.json`. Linux binaries are downloaded
from Meta's official release endpoint and checked against pinned SHA-256 hashes.
`docker/muse.Dockerfile` installs the CLI, Git and ripgrep over the trusted toolkit
image. CLI downloads are cached and rechecked. The binary cannot self-update.

The active generic CLI instructions are **`prompts/muse_coding_agent.md`**.
`prompts/blind_coding_agent.md` remains the direct-API prompt; it is not the CLI
prompt. `prompts/external_coding_agent.md` describes the broader SOP.
Experiment-specific facts belong in `ExperimentRequest`, never the generic prompt.

## Run

```sh
uv run python -m agent_tools --sandbox hypothesis-worker author \
  --request experiment_requests/second_price_auction.json \
  --experiment-id auction_muse_trial
```

Use a fresh experiment ID. The existing sandbox must be a mountless `sbx` shell
sandbox; ordinary Docker also works by omitting `--sandbox`. The worker builds its
trusted base and CLI image as needed. The author command enables the host actor
relay separately for actual LLM policies. To use it, the request must choose
`llm.v1` and the actor model in `MODEL`.

Set `API_KEY`, `MODEL_CODING=muse-spark-1.3` and the independent `MODEL` in `.env`.
The CLI runs `muse exec --model ... --reasoning-effort max --contributor-mode off
--json`. No `--max-model-steps` cap is passed. Each authoring stage has a bounded
wall time and output size; it can contain many CLI-managed model/tool calls.
Controller call counts therefore count **authoring stages**, not provider calls.
Native usage is aggregated per run (without double-counting cumulative updates)
and propagated into ModelResponse token fields. `usage.json` retains provider-call,
cache and reasoning counters plus availability and scope. Unknown usage is not
a claim of zero cost.

Muse Code is an authenticated client. Using the CLI with an API key still makes
provider calls and uses API-key billing; the difference is that Muse manages the
coding/tool loop rather than our controller issuing one large structured model
response per stage.

## Isolation and credentials

One experiment gets one persistent authoring container, workspace, private Muse
home and session UUID. Planning, implementation and repairs append to that session
using `muse exec --session-id`. Current-trial conversation, discoveries, prototypes
and notes survive stage changes. Controller inputs and frozen tests are mounted
read-only; offline validation remains separate. No host checkout, `.env`, user home,
Git history, Docker socket or another experiment's Muse home/workspace is mounted.
See [lifecycle and explicit resume/cleanup](authoring_workflow.md#continuity-and-frozen-tests).

The API key is delivered once over stdin to the trusted container entrypoint,
then passed through the CLI’s `--api-key-stdin` option. It is absent from image
layers, Docker arguments, environment variables and workspace files. Literal keys are redacted from exported events;
responses containing the literal key are rejected. As with an ordinary coding
CLI, **the authenticated CLI process is trusted with that runtime credential**.
This is not a claim that the CLI is isolated from its own credential. Use a narrowly scoped key appropriate for this worker.

The CLI uses `--yolo` only inside this disposable Docker container: Docker supplies
the isolation boundary without requiring nested bubblewrap privileges. The outer
container remains non-root, read-only except its workspace and temporary home,
with dropped capabilities, no-new-privileges and CPU/memory/process limits.
Authoring needs network access to Meta; the separate **validation/simulation
worker remains `network=none` and receives no key**. Actual actors call the host
relay rather than inheriting the CLI credential.

For the existing local sandbox, the only added network allowances are
`lookaside.facebook.com:443` (official download) and `api.meta.ai:443` (model
service), scoped to `hypothesis-worker`. Other installations must allow these
endpoints under their own policy. Do not replace a deny policy with unrestricted
networking.

## Authoring and verification

The CLI writes normal files, avoiding a giant code-containing JSON answer:

- Default complete candidate: `draft.json` holds native configuration/manifest
  data, `tests/` holds grounded cases, and `experiment_extension/` holds code and
  notebook generators. `summary.txt` describes the candidate.
- `author-check` performs the local offline gates and writes a Pydantic-validated
  `response.json` when ready. Collection itself never imports generated Python;
  tests, composition and preview imports run only in container subprocesses.
- The explicit legacy mode retains separate planning/implementation submissions.
  `python -m extension_worker.muse assemble` remains a data-only assembler.
- A `review.json` can terminate a stage with a structured capability/revision gap.

The controller reads only the response, applies its existing static plan review,
normalizes formatting, seals the complete candidate before live calls, and runs
all existing validation gates in the offline worker. A CLI exit code of zero is
not experiment acceptance. Notebook generation/execution, event replay, custom
verification and actual LLM actor calls remain validation-worker responsibilities.
Repairs receive only the current trial's prior artifacts and failed checks.

Audits live under `experimental_components/_authoring/<id>/muse/`, including the
pinned image, actual CLI instructions hash and redacted JSONL events. Source bundles
and completed notebooks/results retain the existing versioning/export conventions.

## Reporting and observability updates

New simulation plans require the [explanatory report contract](explanatory_notebooks.md).
The coding prompt remains general; experiment facts live only in the current request.
The CLI reads current execution capabilities separately from scientific inputs.

Each stage retains incremental `native-events.jsonl`, readable `progress.jsonl`,
`usage.json` and a concise event/exit summary. Console output summarizes tool
descriptions, failures, retries, elapsed time and a heartbeat while waiting; it
does not print each token/lifecycle event. Validation reports its check stages.

The new coding agent authors acceptance tests during the current trial's planning
stage. The controller freezes those files before implementation and materializes
them under read-only `/inputs/frozen_tests/tests`. These are not tests from an
earlier experiment. A repair retains the current workspace and overlays that trial's
returned/normalized implementation files. No other experiment, old result or old session is
staged. This reduces reconstruction without sharing historical state. Because the
same agent authors both tests and implementation, passing these tests is correlated
evidence, not independent proof; separately maintained toolkit checks retain their
own scope and limitations.

On terminal failure, the controller first stops the coding container, then uses a
separate offline, resource-bounded reader to salvage allowed source/draft files as
`partial_workspace.json`, explicitly unapproved. Native events and sanitized failure
metadata survive time/output limits. Symlinks, oversized files and literal
credentials are refused. Salvaged files never count as a completed response.

See [the authoring workflow guide](authoring_workflow.md) for the staged interface
map/starter, central actor settings, offline problem/theory preview, supported
`preview`/`report` commands, one primary live execution and completion rule.
The preview never substitutes synthetic results or a prediction for LLM behavior.
