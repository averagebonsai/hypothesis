# Vector allocation v1 — implementation and trial report

## What this trial was

This was an end-to-end infrastructure demonstration authored and operated by the
assistant in this conversation. The assistant acted as the coding agent: it chose
the example, wrote the gap analysis, implementation, tests and fixture, then used
the new tooling to validate and run that bundle in Docker.

No separate Muse/coding-model API request was made using the project's API_KEY or
MODEL. No independently prompted coding agent generated this bundle. The runtime
actor also did not use an LLM: its action was an intentionally configured scripted
fixture. The demonstration therefore evaluates the extension plumbing and a known
mathematical case, not autonomous generalisation by a separately invoked model.

## The problem and its result

One actor allocates a budget between two projects:

```text
x1 >= 0, x2 >= 0
x1 + x2 = 10
score = -((x1 - 8)^2 + (x2 - 6)^2)
```

The desired target (8,6) requires 14 units, while the available budget is 10.
The best feasible allocation is (6,4): reducing both target coordinates by two
minimises squared distance while meeting the budget.

| Result | Allocation | Score | Where it came from |
|---|---|---:|---|
| Primary actor decision | (5,5) | -10 | Hardcoded input to the existing ScriptedPolicy in job.example.json |
| Mathematical benchmark | (6,4) | -8 | Computed by the new projection helper and solver adapter |
| Possible improvement | — | 2 | Existing benchmark reporting and best-response interface |

The benchmark did not replace the primary action. The value (6,4) is an expected
answer in the tests; the implementation computes it from the target and budget,
rather than returning a hardcoded answer. The helper accepts vectors of dimension
at least two. The main end-to-end fixture exercises two dimensions.

The benchmark uses the existing equilibrium result format. With one actor, a Nash
optimum is simply that actor's own objective optimum; this is not evidence of a
multiplayer equilibrium solver.

## Existing toolkit pieces reused

| Existing building block | How it was used |
|---|---|
| FrozenModel and Pydantic | Strict typed parameters/payloads, JSON transport and finite-value validation |
| Actor, ActionSpace, Action, WorldConfig, WorldState, Outcome, TransitionResult | Existing actor, action, state and consequence contracts |
| Mechanism | Parent for allocation rules, feasibility checks, scoring and transitions |
| MechanismGameView | Shared snapshot-isolated delegation to the mechanism's payoff evaluation |
| BestResponseGameView and BestResponseResult | Exposed the vector optimum and the improvement over a supplied action |
| Solver.solve and SolveResult | Existing checked solver template and equilibrium result envelope; the extension implements _solve |
| MethodContract and requirement evidence | Recorded the specific quadratic/simplex assumptions and analytical justification |
| ScriptedPolicy / scripted.v1 | Emitted the configured (5,5) action; no new policy was needed |
| SimultaneousProtocol / simultaneous.v1 | Scheduled one action from the single actor in one round |
| ComponentRegistry and compatibility preflight | Validated schemas, component composition and solver/view pairing |
| JobManifest, JobRunner and LocalBackend | Ran the existing experiment flow inside the isolated worker |
| BenchmarkRunner | Compared primary and benchmark actions/payoffs and reported improvement |
| Canonical event snapshots, replay and JSON roundtrips | Recorded and checked committed states without calling a model again |

No new simulation execution loop, actor-memory system, recording mechanism,
policy, scheduling protocol, or global component-library entry was created.
Experimental registrations existed only in a fresh worker-local registry.

The existing scalar optimizer and numerical Nash solver were not called for the
projection. NumPy/SciPy optimization routines were not used to implement it; the
helper uses ordinary Python sorting and arithmetic. Their presence in the trusted
framework image does not mean they solved this example.

## Experiment-specific code written from scratch

All of the following are in
[experiment_extension/allocation.py](experiment_extension/allocation.py).

| New piece | Responsibility |
|---|---|
| AllocationParameters | Positive budget and finite target vector, dimension at least two |
| AllocationPayload | Typed allocation vector |
| project_simplex | Implementation of the known sorting/threshold algorithm for Euclidean projection onto a fixed-budget nonnegative simplex; includes arithmetic and feasibility checks |
| AllocationMechanism | One-actor rules, vector dimension/nonnegativity/budget checks, quadratic scoring, and the public-state transition |
| AllocationGameView | Read-only payoff adapter with a projection-based best response |
| AllocationSolver | Thin adapter producing the existing single-actor equilibrium/optimum result using the projection helper |
| CONTRACT_DATA and requirement evidence | Declared the narrow mathematical scope and recorded the quadratic/simplex justification |

This is a new implementation of an established projection method, not a newly
invented mathematical algorithm or a general-purpose vector optimizer.

The assistant also authored [bundle.json](bundle.json), which contains the gap
analysis, exports, domain schemas, method contracts and acceptance criteria;
[job.example.json](job.example.json), the illustrative input fixture; and
[tests/test_allocation.py](tests/test_allocation.py), the five bundle test cases.

## Where the coding-agent prompt lives

The external coding-agent instruction document is
[prompts/external_coding_agent.md](../../../prompts/external_coding_agent.md).
It refers to the fuller [SOP](../../../prompts/newsimulation.md) and
[operator workflow](../../../docs/experimental_workflow.md).

This file is a proposed persistent instruction prompt, not an automatically
installed system message. No current agent_tools or extension_worker command
loads it into a coding model or launches a separate coding agent. The Docker
worker only validates and executes an already authored bundle; it does not decide
what code to write.

For a real external-agent trial, the chosen coding-agent application must receive
these instructions explicitly, together with the experiment request, toolkit
inventory and access to approved file-editing/validation tools. An API integration
would load the instruction text into the provider's supported persistent
instruction channel; an existing coding-agent application could instead be
configured to read and follow it. Referenced SOP/framework files must also be
made available to that authoring agent. Merely storing a Markdown file in the
repository does not make an arbitrary agent follow it.

That authoring-side integration has not been built or exercised in this trial.
The assistant in this conversation already had the user's requirements and wrote
the bundle itself. These coding-agent instructions are separate from LLMPolicy
prompts for actors taking actions inside a simulation.

## Workflow infrastructure created alongside the trial

These tools were new work in the same development phase. They were not an already
finished external-agent system independently evaluated by this demonstration.

| New infrastructure | Purpose |
|---|---|
| agent_tools.specs | Typed capability/gap reports, extension specifications, acceptance declarations, limits and receipts |
| agent_tools.inventory | Registry/shared-tool discovery and curated scalar/vector compatibility checks |
| agent_tools.bundles | Data-only inspection, link/file rejection, content hashing, sealing and exact-byte staging |
| agent_tools.process and DockerWorker | Bounded CLI transport, trusted image preparation, restricted containers and cleanup |
| agent_tools CLI | Inventory, seal, inspect, sandbox preparation, validation and run commands |
| extension_worker | Container-only imports, approved-parent checks, namespaced registry overlays and validation orchestration |
| Dockerfile and framework contract test | Locked framework image and an integration test outside the experimental bundle |
| SOP and external-agent instructions | Instructions for an external agent; no model-calling generator or automatic repair controller |

The image uses uv and the project's locked dependencies. Ruff, mypy and pytest
perform linting, static type checking and test execution. Docker's sbx shell
sandbox provides a private Docker Engine; the inner container runs the bundle.
No new numerical dependency was added for this experiment.

## How validation and execution were performed

The host treated extension files as bytes and JSON. It did not import the extension
or execute its tests. The operator tools copied only trusted build inputs into a
mountless Docker sandbox named hypothesis-worker and built the worker image there.

The sealed bundle and a temporary job manifest were then supplied read-only to an
inner container. That container ran as UID 10001, with no network, no Docker socket,
no API credentials, no extra Linux capabilities, and no privilege escalation.
The configured limits were 2 CPUs, 2 GiB memory with swap disabled, 128 processes,
180 seconds of wall-clock time, 4 MB combined command output and 256 MiB scratch
/tmp. The source, framework files and bundle were read-only.

Within that container the worker:

1. Ran Ruff and mypy against the extension.
2. Ran the bundle's tests plus the framework-maintained integration test.
3. Ran existing framework regressions.
4. Checked that declared acceptance cases actually executed.
5. Constructed and preflighted the worker-local registry.
6. Ran the existing JobRunner flow and returned its result and benchmark.

Results were retained in a receipt binding the exact original bundle digest,
image ID, framework/dependency digest and resource limits. Temporary staging and
inner containers were removed. The outer sandbox was stopped, retaining its images
for subsequent use.

## Tests and observed outcomes

| Check | What it checked | Observed outcome |
|---|---|---|
| Known projections | (8,6), budget 10 -> (6,4); (8,-2), budget 3 -> (3,0); (-3,-3), budget 2 -> (1,1) | Passed |
| Invalid parameters | Negative budget and nonfinite target rejection | Passed |
| Independent feasible grid | Substituted x2=10-x1 and checked 1,001 feasible points against score -8 | Passed |
| End-to-end comparison | Primary (5,5) retained, computed optimum (6,4), payoff difference/improvement 2 | Passed |
| Actual worker restrictions | Nonroot UID, failed writes, no socket/.env, failed outbound connection and bounded PID count | Passed |
| Framework integration case | Existing runtime, canonical replay, private-state ownership and JSON roundtrip | Passed |
| Framework regressions | Existing toolkit and new host-tool tests | 207 passed, 1 opt-in live test skipped |
| Ruff / mypy / declared-test coverage / composition | Lint, installed parent types, required test execution and component preflight | Passed |

There were five test functions in the bundle and one framework integration test,
which is why the isolated acceptance run reported six passing tests.

The first harness attempts found inconsistent Ruff import classification between
host and container, followed by missing py.typed markers on installed toolkit
packages. The assistant diagnosed these manually and fixed the trusted harness
configuration/packaging. The original sealed extension source and acceptance
criteria were unchanged throughout those attempts. Failed receipts were retained.
No automatic coding-model repair loop was exercised.

## What this demonstrates, and what remains untested

The trial demonstrates that the extension workflow can carry a known component
bundle through isolated checks, local registration, the existing runtime and
benchmark comparison while preserving source/result provenance. It also provides
checks against known solutions for this specific mathematical implementation.

It does not measure a separately invoked model's ability to understand an unseen
request, identify the smallest gap, choose the best implementation, or repair
failures. The assistant selected the problem and authored both implementation and
tests. Although the grid calculation is independent of the projection routine, it
was authored by the same assistant and is not a blind held-out evaluation. Finite
grid agreement is not a global mathematical proof. The analytical argument relies
on the known quadratic objective, convex simplex and projection conditions; the
framework records that argument rather than formally verifying it.

The gap-analysis claim also needs qualification: this particular two-variable
problem can be reduced to one scalar with x2=10-x1 and solved using an existing
scalar tool. A direct vector representation was chosen to exercise extension
interfaces and coupled constraints. The trial therefore does not establish that
creating this new solver was necessary or the smallest possible implementation.
The higher-dimensional helper is broader than the two-dimensional end-to-end test.

A genuine external-model evaluation would use an independently specified unfamiliar
request, a frozen toolkit, held-out acceptance cases, and recorded model calls,
repair attempts, token/cost usage and final outcomes. Neither the coding-model
behaviour nor LLM allocation behaviour was evaluated here.

## Provenance and this README amendment

The original tested bundle digest was:

`eb7af6a48d1cb0f2a962f8d7b212d3b99ff19a59ed6862c8d00e2d05d6ba6ce5`

See the [original trial summary](../TRIAL.md) and its linked local receipt for the
actual validation/run result. The original README and seal are preserved in
[the tested-v1 provenance archive](../provenance/v1-tested-eb7af6a48d1c/).

At the user's explicit request, this README was expanded after the trial. This is
a documentation-only amendment: implementation, tests, specification and input
fixture retain their original tested hashes. The seal has been updated to describe
the current documented bundle, and the old seal has not been discarded. The
[amendment record](../provenance/v1-readme-report-amendment.json) records both digests.

The original Docker receipt applies to the original digest, not the new README
bytes. This documentation amendment was checked by comparing all non-README hashes;
it did not rerun Docker tests or make API calls. A future worker run will perform
normal validation against the current seal. This explicit user-authorized amendment
does not relax the ordinary rule requiring a new version for source/test changes.

For operator commands, see
[the experimental workflow](../../../docs/experimental_workflow.md).
