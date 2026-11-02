# Muse Code headless coding worker

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
The CLI event trace is retained; the generic ModelResponse's zero token defaults
mean unavailable usage here, not a claim of zero cost.

Muse Code is an authenticated client. Using the CLI with an API key still makes
provider calls and uses API-key billing; the difference is that Muse manages the
coding/tool loop rather than our controller issuing one large structured model
response per stage.

## Isolation and credentials

Each authoring stage gets a new container, temporary home and workspace. Only the
current task/schema/instructions are mounted read-only. Toolkit code is installed
read-only and inspected on demand. Framework regression fixtures are removed
from the authoring image. No previous experiment directories, host home, `.env`,
Git history, Docker socket or previous Muse sessions are mounted.

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

- Planning: `draft.json` holds native plan/config/manifest data; ordinary `tests/`
  files contain the proposed tests.
- Implementation/repair: `experiment_extension/` contains Python files and
  `summary.txt` describes the change.
- `python -m extension_worker.muse assemble` reads these files as data and creates
  a Pydantic-validated `response.json`. It never imports generated Python.
- A `review.json` can terminate a stage with a structured capability/revision gap.

The controller reads only the response, applies its existing static plan review,
freezes tests/config, normalizes formatting, seals a new bundle version and runs
all existing validation gates in the offline worker. A CLI exit code of zero is
not experiment acceptance. Notebook generation/execution, event replay, custom
verification and actual LLM actor calls remain validation-worker responsibilities.
Repairs receive only the current trial's prior artifacts and failed checks.

Audits live under `experimental_components/_authoring/<id>/muse/`, including the
pinned image, actual CLI instructions hash and redacted JSONL events. Source bundles
and completed notebooks/results retain the existing versioning/export conventions.
