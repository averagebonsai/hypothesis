# Fast authoring without historical experiment access

The external coding agent starts with a concise generated interface guide and
optional domain-neutral templates. Muse receives `/inputs/starter/INTERFACES.md`
and `/inputs/starter/experiment_extension/`; the API backend receives the guide in
its toolkit context. The guide maps responsibilities, data flow, approved component
locations, exact installed parent method signatures, compatibility limits, notebook
contracts and validation commands. It is not an automatic proof that a component
fits: scientific rules, shapes, timing, information and guarantees must match.

```sh
uv run python -m agent_tools guide
uv run python -m agent_tools starter /tmp/new-authoring-starter
uv run python -m agent_tools starter /tmp/new-tool-starter --kind tool
```

Copy only needed templates and replace their explicit `NotImplementedError` stubs.
The starter does not contain a solved experiment, fake passing tests, predicted
LLM behavior or a new mechanism when reuse suffices. Full source remains readable
for specific unresolved questions; reading transport internals is not a prerequisite.

## Continuity and frozen tests

The default Muse backend keeps one authoring container, workspace, private CLI home
and session UUID for the whole experiment. Each stage appends a new instruction
through `muse exec --session-id`; planning discoveries, conversation context, scratch
files, prototypes and notes remain available during implementation and repairs.
The controller refreshes read-only inputs between turns and overlays only returned,
normalized source files. It does not reconstruct the workspace from selected files.

The controller still freezes tests/configuration and runs acceptance, regression,
preview and simulation jobs in separate workers. Freezing prevents acceptance criteria
from being silently weakened; it is not an independent examiner. Stage responses are
removed before each turn so an old response cannot satisfy a new stage. New experiments
receive new session/container/volume IDs, with no mounts of historical experiments.
Session identity binds the experiment, user request, coding model, instructions and
trusted toolkit context. Concurrent turns and cross-experiment reuse are rejected.

SDK users call `agent.close()` after all authoring stages (also on failure); the CLI
closes automatically. This removes only the current session's container and private
volumes, retaining approved versioned bundles and audit artifacts. Explicit
`from_environment(..., resume=True)` can reattach a retained session with matching
audit/context; a stopped container can restart against its retained home/workspace.
A missing or closed session is not silently replaced with empty context. Legacy
fresh-stage trials cannot regain their lost conversation. The explicit legacy API
backend remains stateless; this continuation change applies to the active Muse backend.

## Preview before execution

New simulation plans declare both `NotebookSpec.preview_generator` and `generator`.
Old sealed bundles remain readable and can still use their existing final reports.
The preview callable has signature `(JobManifest, Path) -> Path` and uses
`ReportPreview` / `write_preview_notebook(directory, preview)` to write
`preview.ipynb`. It receives the problem request and resolved configuration, never
an observed or synthetic run. It explains:

- The problem, rules, information and scientific purpose.
- A calculated mathematical reference and theoretical explanation, if available,
  including prerequisites and scope; otherwise why none is provided.
- Assumptions and limitations in normal text.
- Explicitly pending live results, their interpretation and actor rationales.

It must not predict LLM performance or explain nonexistent observations. The worker
executes the preview in a separate offline container without credentials or an actor
relay before the primary run. Structural validation cannot prove prose or theory
correctness; acceptance tests must check mathematical references against grounded
cases. The exported preview can also be read by a human without running actors:

```sh
uv run python -m agent_tools --sandbox hypothesis-worker preview \
  experimental_components/example/v1 --job experimental_components/example/v1/job.example.json \
  --output experimental_components/_runs/example/preview-1
```

## Central actor execution settings

`ActorExecutionSettings` belongs to the operator, separate from scientific problem
inputs. Before plan freeze, it resolves builtin `llm.v1` transport fields: actor
model (`MODEL`), reasoning effort, output tokens, retry attempts and per-actor call
budget. It preserves instructions, personas, permissions and all scientific data.
Defaults: no explicit generation-token ceiling, two attempts per decision, 48 calls
per actor and a shared relay ceiling of 48 calls. For known schedules, preflight
reserves calls for every decision and configured retry; repeated experiments must
set a sufficient explicit shared call budget. Provider-default output limits may
still apply when the cap is omitted. Override
these explicitly through the settings API; `author --actor-output-tokens N` exposes
the common CLI choice. The exact resolved settings are audited, supplied to the
coding agent and enforced by the relay. Coding continues to use `MODEL_CODING` at
maximum reasoning; actor settings never change the coding model.

## One live execution and completion

Acceptance/regression checks use fake or scripted policies. The framework's
composition test preflights scheduling, observations and benchmark compatibility
without calling actors. Only the primary simulation opens the actor relay; that run
also exercises integration, event replay, private-state coverage and recorded-result
verification. Retries inside a single decision remain recorded attempts, not a new
simulation. Explicit simulation probes are separate operator requests, not automatic
acceptance reruns.

The controller stops immediately after successful checks, result and report. If a
failed primary run already attempted live calls or retained a result, automatic
repair does not rerun it: the outcome requires review. If a result exists, repair
its reporting code in a new sealed version and render it from the saved artifact.
The authoring prompt likewise finishes after schema/check/content completion; extra
tool calls must address named outstanding issues. No model-turn cap is reintroduced.

## Supported report-only operation

```sh
uv run python -m agent_tools --sandbox hypothesis-worker report \
  experimental_components/example/v2 --result path/to/saved/result.json \
  --output experimental_components/_runs/example/revised-report
```

This command prepares/resolves the current trusted image, snapshots a sealed bundle,
verifies the saved result matches the bundle's scientific job, reruns applicable
recorded-result checks and executes reporting cells offline. It never calls the
simulation runner or actor relay. The output contains `results.ipynb`, unchanged
saved result data and a distinct report receipt recording input hash, bundle digest,
actual image/framework IDs and zero actor calls. This receipt is not a fresh
simulation receipt and does not claim full source acceptance/regression validation.
A changed scientific job requires an explicit new experiment, not relabelling an
old result. Use fresh output directories; existing artifacts are not overwritten.

## Verification of this change

Offline Docker smoke testing exercised the actual host/container relay with a fake
provider: preview and acceptance made no actor requests, the one-round primary run
made exactly three (one per actor), and saved-result rendering made zero additional
requests. The report kernel executed, preserved the saved result data, and rejected
a result from a different scientific job. No provider API was called. The worker
passed 274 toolkit regression tests (one skipped), plus both smoke acceptance checks.
Host lint and mypy passed (96 source files). This establishes functionality; a new
blind live coding-agent trial is still needed to measure authoring speed gains.

## Persistent-session verification

The lifecycle integration check uses real Docker containers with a fake CLI to
exercise planning, implementation, repair, read-only frozen tests, retained notes
and prototypes, a failed turn, offline source salvage, explicit resume and resource
cleanup. Separately, the pinned real Muse CLI runs with its offline echo provider:
two turns retain the same session journal, while a different UUID excludes the
first trial's marker. These checks make no provider API calls; they do not measure
live model quality, latency or semantic recall. The latest full Docker regression
suite passes 279 tests with one skipped; host tests pass 275 with five skipped.
Native Muse context compaction still applies to conversation history; workspace
notes and source files remain available independently of model context length.

## Temporary output policy and recovery

For the concurrent runtime, typed actor profiles, durable committed-event resume,
timings and the prepared smaller public-goods trial, see [fast simulations](fast_simulations.md).

Explicit generation-token ceilings are disabled by default for both authoring DTOs
and actor policies. `ModelRequest.max_output_tokens=None` is recorded as unset and
omitted from provider HTTP payloads, rather than sent as a null cap. Callers may
still opt into a positive limit. Provider defaults remain provider-controlled.

The local actor-relay socket has no independent generation deadline: provider I/O
and the explicitly configured overall worker deadline own that responsibility.
Long experiments can opt into worker budgets up to 7,200 seconds; the ordinary
default stays 180 seconds. A short hidden socket deadline must not discard a valid
provider response that is still being generated.

`RecordedPrefixGateway` is an operator recovery utility. It accepts an explicitly
supplied current-trial transcript, including resolved retries, and reuses a recorded
response only when model, schema, instructions and observation match. An explicit
operator option permits removing a token ceiling while preserving each replayed
request's authentic original metadata. No experiment directory search occurs.
New calls begin only after the prefix is reconstructed. Receipts distinguish reused
requests from fresh provider attempts. Earlier unresolved failures remain in their
original audit files, not silently relabelled as successful decisions. This is
response-level reconstruction for deterministic mechanisms, not a durable committed
state checkpoint facility; a first-class event/state checkpoint remains preferable.
