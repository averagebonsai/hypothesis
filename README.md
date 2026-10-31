# hypothesis

A composable toolkit for LLM-driven simulations. The shared execution framework supports scripted and generic LLM policies. M2.1 adds
a provider-neutral model gateway and separate finite-game pure-Nash benchmarks.

```sh
uv sync
uv run pytest
uv run ruff check src tests
uv run mypy src
uv run python -m examples.payoff_matrix
uv run python -m examples.measurements
uv run python -m examples.llm_payoff_matrix
```

Open `visualisations/payoff_matrix.ipynb` with the project's `.venv` Python kernel.
The executed notebook calls the generic LLMPolicy with a deterministic fake gateway,
displays actor outcomes alongside the independent pure-Nash benchmark, reconstructs
committed states, shows model-call provenance, and lists configured assumptions.
Its saved outputs are integration fixtures, not live LLM observations.

The shared interfaces are explicit abstract parents:

- `simulation_core.policy.Policy`: observation requirements and a typed decision.
- `simulation_core.mechanism.Mechanism`: config/state/action validation, pure
  evaluation, and domain transition proposals.
- `simulation_core.protocol.ProtocolRules`: actor scheduling, batch legality,
  phase progression, and termination.

`SimulationRuntime` implements the trusted loop. Observations are constructed by
`simulation_core.observation` from per-actor configuration permissions, independently
of scheduling and mechanism code. Actors receive only configured public fields and
their own configured private fields/memory. Permissions select top-level fields;
an allowed field exposes its nested contents. Defaults expose no public/private
facts, while permitting each actor to read and replace its own memory. Policies
may also propose allowed own-private-fact patches. The runtime owns public state,
phase/tick commits, and private updates. Mechanisms may propose private record
replacements (for example, exposure delivery); conflicting mechanism/policy edits
to the same private record fail explicitly. Outcomes may contain no payoffs or
payoffs for a subset of actors; mechanisms enforce domain-specific completeness.

`components.library.standard_registry()` provides approved factories. Its
`describe()` method exposes IDs, parameter schemas, and action schemas as JSON.
Factories create fresh components per run and fresh policies per actor. Arbitrary
module loading is not supported. Mypy checks concrete components against the
abstract parent contracts.

Experiment-specific data is separate from components:

- `src/examples/configs/prisoners_dilemma.json`: actors, action schemas, scripted
  choices, payoff cells, visible state, assumptions, and round count. Expected
  payoffs for A cooperating/B defecting: A=0, B=5.
- `src/examples/configs/measurements.json`: three numeric measurement actors,
  configured private updates, two recording rounds, and metric-only outcomes.

The normal-form mechanism supports arbitrary actor IDs, any positive number of
actors, asymmetric finite choices, explicit payoff cells, and configurable output
fields. The recording mechanism collects arbitrary schema-validated actions.
The simultaneous protocol and scripted policy have no experiment-specific fields.
Tests also cover an asymmetric three-player normal-form game and an active-actor
subset, alongside privacy, validation, replay, mutation, and isolation checks.

To add an experiment, inspect the registry, populate `SimulationConfig` JSON, and
run it through the same runtime. If a component is missing, implement the relevant
abstract parent, register its trusted factory and schemas, and test it without
changing the runtime. There are no hidden textbook defaults in the core; any
experiment-building defaults must be recorded in configuration assumptions.

Internal event snapshots are the canonical committed record and include private
state; never provide them to actors. Replay makes no policy or mechanism calls.
M1 logging is in-memory, and the local runner is for trusted components. Durable
storage, redacted export, stochastic mechanisms, continuous numerical solvers, and
isolated untrusted extensions remain future milestones.


User requests and temporary jobs
-------------------------------

`ExperimentRequest` is the Pydantic contract for an incomplete user hypothesis,
supplied inputs, and requirements. A creating agent resolves it into the separate
`SimulationConfig`. The contracts do not yet perform natural-language compilation.
Component parameters are validated against registered Pydantic models. The registry
also exposes request and resolved-config JSON schemas for agent discovery.

`Assumption` records an exact JSON Pointer, value, source, rationale, and optional
reference. Validation rejects stale values, missing paths, and duplicate paths.
`JobManifest` binds request to config and verifies supplied inputs that have explicit
target paths. Free-text requirements and unmapped inputs require agent interpretation.

```python
from components.library import standard_registry
from simulation_core.execution import JobRunner, LocalBackend
from simulation_core.request import ExperimentRequest

request = ExperimentRequest(hypothesis="What happens under these choices?")
# config is a fully resolved SimulationConfig, authored with registered schemas.
artifact = JobRunner(LocalBackend(standard_registry())).run(request, config)
# artifact.manifest retains request/config; artifact.result contains outcomes/events.
```

The runner serializes a versioned job manifest into a temporary directory, executes,
and deletes the directory on success or failure. It does not persist results/configs.
The returned in-memory artifact retains provenance and can be explicitly exported.
`examples.payoff_matrix.run_job()` demonstrates this path; `run_experiment()` returns
only its RunResult for convenience. Checked-in config/request JSON files remain
stable test fixtures. Full artifacts include private data and require restricted access.
LocalBackend is trusted in-process execution, not a security sandbox. Future isolated
workers should preinstall the core/approved library and accept job manifests; arbitrary
extensions require a separate isolated code bundle and must not run in LocalBackend.

LLM policies and mathematical benchmarks
---------------------------------------

`LLMPolicy` implements Policy and uses an injected `ModelGateway`. Its bounded
request contains only configured instructions/persona, the actor's authorized
observation, and its declared action payload schemas. Responses must supply one
schema-valid action, optional own-memory replacement, permitted private patches,
and a required nonempty concise rationale. Generic JSON updates travel as key/value_json
entries so strict provider schemas need no open-ended objects. Duplicate keys,
nonfinite values, impersonation, malformed JSON, and disallowed writes are rejected.
Runtime independently checks action ownership, schemas, domain legality, and writes.
There is no hidden conversation state; only committed private memory is resupplied.

A shared per-job BoundedGateway limits calls, request/response sizes, and output
tokens per call. LLMPolicy separately bounds attempts and calls per actor. These
are call/token limits, not a dollar-price estimate. Provider transport has a timeout
and no hidden retries. Committed events and RunResult retain prompt/response call
records, provider request IDs, actual/requested model IDs, and usage. Failed
LLM decisions raise LLMPolicyError with the failing policy's call records and do not
commit an incomplete action batch. Replay never invokes a gateway.

`Solver` and `GameView` are general mathematical interfaces. PureNashSolver uses
only a finite read-only GameView. NormalFormGameView adapts the selected mechanism
without duplicating payoff equations. The solver has a profile budget and payoff
tolerance; it reports solved, multiple, no_pure_equilibrium, or budget_exhausted.
It makes no claim about mixed equilibria. Every equilibrium is retained.

BenchmarkSpec explicitly selects solver/view/parameters and the compared tick
(default: final committed tick), with a complete-information assumption. BenchmarkRunner
uses an isolated copy of that tick's precommit state. JobResult.benchmark contains
all equilibrium comparisons, actor-minus-equilibrium payoff deltas, action
differences, unilateral deviation gains (regrets), and a config SHA-256. Expected
benchmark failures report separately from the primary actor run; programming errors
propagate for diagnosis. No benchmark action replaces an actor action.

Offline demonstration:

```python
from examples.llm_payoff_matrix import run_llm_job
artifact = run_llm_job()  # generic LLMPolicy, deterministic FakeGateway; zero API calls
print(artifact.benchmark.result.status)
print(artifact.benchmark.comparisons[0].payoff_deltas)
```

The fixture chooses cooperate/defect: payoffs (0, 5), compared with the unique
pure-Nash defect/defect payoffs (1, 1). Deltas are (-1, +4); regrets are (1, 0).
Fake and live modes are explicitly labeled in call records and the notebook.

Live test setup:

1. Set API_KEY and MODEL in the project .env (or environment); OPENAI_API_KEY and
   OPENAI_MODEL remain supported aliases. The model
   is explicit; no provider/model is selected silently and no credentials go into
   manifests, actor configuration, source files, or notebook cells.
2. In the notebook set USE_LIVE_API = True and rerun. Or call
   `examples.llm_payoff_matrix.run_live_job()` from Python.
3. Optional live pytest: `RUN_LIVE_LLM_TEST=1 uv run pytest tests/test_llm_policy.py -k live`.
   The ordinary suite skips it and mocks all provider calls.

The OpenAI and Meta adapters use Responses API structured output with strict JSON Schema,
refusal/incomplete handling, no response storage request, and bounded HTTP reads.
See [official OpenAI documentation](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
Generic policy/gateway contracts do not depend on OpenAI. Registration of llm.v1
requires an injected gateway; the default registry has no network-enabled policy.
The job helper creates a fresh shared bounded gateway per run. Execution remains
trusted and in-process; model adapters do not provide untrusted-code isolation.


Per-action explanation traces and the live Contributor run
---------------------------------------------------------

Every LLM response must include a nonempty, concise stated decision rationale;
null/blank explanations are retried and rejected within the normal call budget.
This is the model's stated explanation, not its private internal reasoning.
Decision.rationale is retained in each Event.decisions record and linked to the
accepted ModelCallRecord.rationale. Replay checks action/rationale links and never
recalls the model. ScriptedPolicy reports that it emitted a configured action.

The runtime emits one JSON logging entry per committed action to simulation.actions.
Use stream_action_trace() to enable console output; traces remain in events even
when console logging is disabled. The notebook enables streaming and prints a
per-turn explanation table after execution.

LiveModelSettings loads API_KEY/MODEL from the nearest project .env, including when
a notebook runs from visualisations/. Explicit process environment takes precedence,
and the optional model argument overrides MODEL. Credential serialization is excluded.
Muse model IDs select the MetaResponsesGateway at api.meta.ai; other models retain
the OpenAI adapter. The generic LLMPolicy is unchanged across providers. For Muse,
the example explicitly records low reasoning effort in its policy config.
See [Meta's API overview](https://dev.meta.ai/docs/overview),
[structured output](https://dev.meta.ai/docs/structured-output), and
[reasoning settings](https://dev.meta.ai/docs/reasoning).

The saved notebook is now a LIVE muse-spark-1.3-contributor run: A and B both chose
defect and received payoff 1, matching the unique pure equilibrium. Both explained
that defect yields a greater own payoff for either rival move. These are actual
model responses; the older fake-gateway cooperate/defect result was hardcoded only
inside examples.llm_payoff_matrix.fake_response. Flip USE_LIVE_API to False for
that deterministic fixture; leaving it True makes billed API calls on re-execution.
