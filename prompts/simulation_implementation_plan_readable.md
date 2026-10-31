# Simulation Builder — Human-Readable Implementation Plan

**Status:** Proposed architecture for human review. Not all decisions are final.  
**Audience:** Human reviewer first; coding agent second.  
**Stack:** Python 3.12+, `uv`, Pydantic v2; NumPy/SciPy for economic models.  
**Companion:** `simulation_interfaces.py` is a *reference contract*, not a demand to implement every class immediately.

## 1. What are we building?

A user describes a hypothesis: “What happens to prices when a competitor enters?” or “How might different consumers react to this advertisement?” A coding agent turns the request into a **simulation specification**, using reusable components where possible. A trusted simulation engine executes that specification and reports results, assumptions, limitations, and for LLM actors, recorded inputs/outputs and an optional concise decision rationale. 

We want one engine that can support both (a) mathematical microeconomics, such as Bertrand, Cournot and Stackelberg competition, and (b) turn-based behavioral simulations, such as LLM consumers reacting to ads or discussing products. 

**The essential loop is simple:** establish a world → identify who acts → give each actor permitted information → obtain actions → apply the consequences → update the world → repeat or finish. A mathematical solver may determine a joint set of actions instead of asking actors to decide individually.

**Important:** A correctly executed simulation is not automatically a reliable prediction. LLM personas and arbitrary parameters produce *hypothetical scenarios* until validated against real-world evidence.

**Important:** In production, all agents within this simulation engine will be LLM agents. However, for initial testing for each milestone, we will begin with implementing mathematical agents to prove the economic experiment produces its expected results, and subsequently swapping them out for LLM actors. 

## 2. One concrete example to keep in mind

**Question:** Two coffee shops compete on price. If Shop A improves quality, what happens to equilibrium prices, sales, and profits?

- **Actors:** Shop A and Shop B. Each can choose a nonnegative price. Consumers need not be individual actors: three consumer groups can be represented in aggregate.
- **World configuration:** Shop attributes, costs, consumer group populations, price sensitivities, and baseline quality.
- **World state:** Prices and resulting quantities/profits in the current round, plus phase and history where relevant.
- **Policy:** A firm seeks to maximize profit; it needs a well-defined objective and assumptions about the rival.
- **Mechanism:** Given both prices, a demand model calculates purchases and a payoff model calculates profit.
- **Protocol:** Both firms choose prices simultaneously; neither sees the other's uncommitted price.
- **Solver:** A Nash solver finds mutually optimal prices by evaluating hypothetical price combinations.
- **Experiment:** Compare a baseline (Shop A quality 6) with treatment (quality 8), using the same model.

The *same engine* should later handle an ad experiment by replacing firms with consumer actors, profit-maximizing policies with LLM policies, and the market mechanism with exposure/response rules. No changes to the core execution loop should be needed.

## 3. Components: what each owns, and what it must not do

### 3.1 Actor — who participates?

An `Actor` describes a participant, its identity/persona, its **experiment-specific action space**, and the policy assigned to it. **Agreed:** action space belongs to the actor. A Bertrand firm only needs `set_price`; we do not list irrelevant actions such as exiting the market. The protocol determines *when* it may act, not a second list of capabilities.

An actor **does not** choose its own action, compute demand, schedule turns, or secretly own changing simulation state. Keep identity/attributes in the actor definition; keep changing beliefs, memory, and actions in world state. Memory is nested within each actor’s private state, not a separate world-level store.

### 3.2 Policy — how is an action selected?

A `Policy` maps an actor's permitted observation (and, if necessary, a restricted decision service) to an action. Implementations can be LLM-based, scripted, random, or profit-maximizing.

**Example:** A profit-maximizing policy chooses a price based on an objective; it **does not define the demand equation**. That belongs to the mechanism. An LLM policy can read the actor's permitted memory but cannot mutate the world directly. If memory must change, return a typed Decision containing the action and an optional replacement for its own private memory for the runtime to commit. There is one action per active actor per turn. Policies cannot address another actor’s private state.

### 3.3 WorldConfig and WorldState — what exists, and what is true now?

`WorldConfig` contains initial/exogenous assumptions: costs, populations, network connections, product attributes. `WorldState` contains evolving facts: prices, beliefs, observed messages, pending actions, turn number, and results. Do not confuse either with `ExperimentConfig`, which describes what research comparison to run.

A world state is **authoritative**. Policies receive only a filtered `Observation`, never unrestricted world access.

### 3.4 Observation — what does this actor know before acting?

An observation is a typed snapshot created from world state according to the information rules of the protocol. The policy can declare required inputs; the observation builder supplies only *authorized* fields. If required fields are unavailable, validation should fail rather than silently leak information.

**Stackelberg example:** After the leader commits quantity, the follower's observation includes that quantity. Before the leader commits, the follower must not see a future quantity. For repeated games, an actor's permitted past observations and beliefs may be exposed as memory. Memory is not identical to the full world state.

### 3.5 Mechanism — what consequences follow from actions?

Demand equations, cost and payoff calculations, market clearing rules, ad exposure, message delivery, and automatic belief changes belong to the mechanism. Prefer composition: a `BertrandMechanism` can use reusable `DemandModel`, `CostModel`, and `PayoffModel` objects.

Two operations are useful:

- `evaluate(state, candidate_actions)` computes **hypothetical** consequences without changing the state. Solvers may call it thousands of times.
- `transition(state, committed_actions)` produces the **next** world state after actions are accepted.

Do not let `evaluate` mutate world state, write to persistent memory, or consume uncontrolled randomness. In simple models, `transition` can reuse `evaluate` and package its result into a state update.

### 3.6 Protocol — who acts when, and what can they observe?

A `Protocol` controls active actors, simultaneous versus sequential timing, when actions become visible, and termination. It does **not** calculate profits or select prices.

- **Bertrand:** Both firms submit prices before either submission is revealed.
- **Stackelberg:** Leader commits quantity, then follower observes it and chooses quantity.
- **Ad study:** Exposure → optional discussion rounds → final response.

In v1, an active actor may use its entire actor-defined action space. Phase-dependent action restrictions are a future extension only if required.

### 3.7 Solver — do we need a mathematical solution?

A `Solver` is **optional**. It searches for a solution concept such as Nash equilibrium, backward-induction equilibrium, or market clearing. It repeatedly calls the mechanism's read-only evaluation interface, then returns candidate actions plus diagnostics. It must not commit changes itself.

**Policy-driven run:** The runtime asks each active actor's policy for an action. Useful for LLM consumer behavior, repeated heuristic pricing, and social interaction. **No equilibrium is guaranteed.**

**Solver-driven benchmark run:** A separate fresh benchmark world invokes a solver for a joint action profile, validates it, then commits it. The primary production trajectory remains LLM policy-driven. Compare its realized actions/outcomes with the mathematical benchmark; do not overwrite actor decisions with equilibrium actions. Useful for textbook Bertrand, Cournot, and Stackelberg solutions. A solver result must include convergence/residual diagnostics; never silently claim equilibrium on numerical failure.

The same runtime can use a pluggable `ActionResolver` internally, but **do not require the human-facing design to revolve around that helper class**.

### 3.8 Experiment — what question are we investigating?

A `SimulationConfig` defines **one run**. An `ExperimentConfig` defines how to organize one or more runs: hypothesis, baseline/treatments, outcome measures, repetitions, seeds, and comparisons. An experiment is useful even with one condition (e.g., repeated stochastic trials), but should not be mandatory for a simple simulation.

The experiment must not duplicate the mechanism's equations or the protocol's scheduling logic.

### 3.9 Runtime — who is in control?

The runtime is **trusted, maintained code**. It loads validated configuration, creates initial state, obtains authorized observations, asks policies or a solver for actions, validates actions, calls `transition`, validates the new state, records events, and enforces termination/resource limits. The coding agent must **not** rewrite this loop per experiment.

## 4. The complete Bertrand execution, step by step

1. **Compile:** Coding agent reads the user request and selects existing firm actors, segmented-logit demand, a profit model, simultaneous protocol, and Nash solver. Missing numeric parameters must be supplied, explicitly assumed, or flagged for review—not silently presented as calibrated facts.
2. **Validate:** Pydantic validates actor/action types, positive populations, nonnegative costs, price-sensitivity constraints, and matching firm/segment dimensions.
3. **Initialize:** Runtime creates a baseline world from `WorldConfig`.
4. **Construct game:** Protocol establishes simultaneous pricing and authorized information. Solver receives a read-only payoff-evaluation service.
5. **Search:** Solver tries candidate price pairs. Each candidate goes through `Mechanism.evaluate`; none modifies the world.
6. **Check:** Solver returns candidate equilibrium prices and best-response residuals. Runtime rejects invalid actions or failed solution criteria (or reports failure clearly).
7. **Commit:** Runtime calls `Mechanism.transition` once to produce the final baseline state and logs the event.
8. **Intervene:** Experiment creates a **fresh** world with Shop A's quality changed, preserving the baseline separately.
9. **Repeat and compare:** Run the same solver and mechanism, then calculate differences in prices, quantities, profits, and shares.

For **Stackelberg**, the solver must account for the follower's contingent best response when choosing the leader's quantity. A naive two-turn forward loop alone does not solve Stackelberg equilibrium.

## 5. A second use case: advertisement reception

**Question:** Which of two advertisements produces higher simulated purchase intent among students and professionals?

- **Actors:** Individual simulated consumers, each with persona, action space (`rate_ad`, `comment`, optionally `share`), and an LLM policy.
- **WorldConfig:** Ads, products, population/persona distribution, channel, and optionally a social network.
- **WorldState:** Exposure records, private opinions, messages, memory, and responses.
- **Protocol:** Assign ad → expose → collect response; optionally allow two discussion rounds.
- **Mechanism:** Delivers exposure/messages and records valid response outcomes; any automatic belief-update rule must be explicitly defined.
- **Solver:** None. Runtime collects policy actions directly.
- **Experiment:** Compare arms and report scores, qualitative themes, and variation across seeds/personas.

**Scientific warning:** 100 LLM respondents are not equivalent to a random sample of 100 humans. Treat results as exploratory synthetic feedback unless validated against human data.

## 6. How the coding agent should build experiments

**Default: configuration, not custom code.** The agent should first inspect the registry of available components, then generate a typed `SimulationConfig`/`ExperimentConfig` that references them. If it cannot express the experiment, it may propose a new component implementing an existing interface. A human reviews that extension before promotion into the reusable library.

The agent should produce: (a) plain-language interpretation of the hypothesis, (b) explicit assumptions and missing inputs, (c) selected components, (d) configuration, (e) new extension code only if needed, and (f) tests and expected outputs. It must never alter the trusted runtime to make an experiment pass.

## 7. Isolation and `uv`

`uv` manages project dependencies and reproducible environments; it is **not a security sandbox**. Use it for development and pinned worker dependencies. Use a separate isolated worker for generated code.

**Development setup (illustrative):**

```bash
uv init simulation-platform
cd simulation-platform
uv add 'pydantic>=2,<3' numpy scipy
uv add --dev pytest ruff mypy
uv run pytest
```

**Production execution:** The host validates a job, launches a prebuilt restricted worker container, passes a read-only job directory, receives structured results, and terminates the worker. Do not let generated code import into the host controller. Start with a Docker-backed worker for development; harden isolation and resource cleanup before multi-user deployment. A Docker image may use `uv sync --frozen --no-dev` during its build rather than `pip install`.

For LLM actors, a network-isolated worker should call a **trusted model gateway** rather than receive provider API keys or unrestricted network access. Restrict requests, costs, and model permissions.

## 8. Suggested source files

```text
simulation-platform/
  pyproject.toml
  uv.lock
  simulation_core/
    types.py          # Actor, Action, Observation, typed IDs
    world.py          # WorldConfig, WorldState, memory
    policy.py         # Policy interface
    mechanism.py      # Mechanism interface; evaluation results
    protocol.py       # Protocol interface; observation rules
    solver.py         # Solver interface; diagnostics
    experiment.py     # SimulationConfig, ExperimentConfig
    runtime.py        # Trusted execution loop
    validation.py     # Invariants and checks
    registry.py       # Approved component lookup
  components/
    economics/        # Demand, cost, payoff, equilibrium models
    policies/         # LLM, optimization, scripted policies
    protocols/        # Simultaneous, sequential, repeated
    advertising/      # Exposure and response mechanisms
  worker/
    main.py           # Isolated job entrypoint
    Dockerfile
  examples/
    bertrand/
    stackelberg/
    advertisement/
  tests/
```

The companion `simulation_interfaces.py` has `FILE:` separators to guide splitting. **Do not blindly implement every suggested interface**; implement only what each milestone requires, keeping the public contracts coherent.

## 9. Implementation milestones and acceptance tests

### Milestone 1 — Minimal runtime, no LLMs

Implement typed Actor/Action/World, Policy, Mechanism, Protocol, and runtime. Make a simple two-player payoff-matrix game execute with scripted actions. **Pass:** invalid actions are rejected; observations cannot expose prohibited fields; the event log reproduces the sequence.

### Milestone 2 — Economic evaluation and solvers

**Accepted first increment:** M2.1 implements LLM policies and separate finite-game benchmarks before this original economic/numerical scope (M2.2). Offline implementation and tests are complete; live verification awaits credentials/model selection. See sections 15–16.

Implement linear demand, costs, payoff evaluation, numerical optimization, and a Nash solver. **Pass:** monopoly and Cournot cases match analytical benchmarks; solver failures report residuals; hypothetical evaluation leaves state unchanged.

### Milestone 3 — Bertrand and Stackelberg

Implement differentiated Bertrand (including outside-option segmented logit) and Stackelberg quantity leadership. **Pass:** both run without editing `runtime.py`; Stackelberg leader anticipates follower response; feasible quantities and actions are enforced.

### Milestone 4 — Experiment comparisons

Add treatment/control generation, fresh worlds, repetitions, metrics, and seeded randomness. **Pass:** baseline/treatment runs do not contaminate each other; results retain assumptions and provenance.

### Milestone 5 — LLM advertising actors

Add LLMPolicy and structured response validation, actor memory, and ad-exposure mechanism. **Pass:** no unapproved information leakage; outputs follow response schema; multiple rounds preserve state correctly.

### Milestone 6 — Custom extensions and sandbox

Add registry, generated mechanism/policy loading in isolated workers, and `uv`-built worker image. **Pass:** an extension can run without host-side import; time/resource limits and error handling are tested; the controller stays unchanged.

### Milestone 7 — Social interaction and validation

Add message delivery, network interactions, sensitivity analysis, and empirical benchmark reporting. **Pass:** social simulation runs with the same core loop; synthetic-versus-validated status is explicit.

## 10. Human review checklist (resolve before coding each milestone)

- [ ] Do we agree actor action spaces are fixed per simulation in v1? 
--- Yes. 
- [ ] Which world fields are public, private, or derived? Who specifies the observation permissions? 
--- Proceed with textbook implementation of experiments unless otherwise specified by user. Ambiguous choices should be listed in a list of assumptions at the end of the simulation (e.g for this particular simulation, assume that agents observe each other's actions and their own profit levels but not each other's profit levels.)
- [ ] Should actor memory updates be separate actions or part of a typed transition result?
--- Part of a typed transition result. WorldState gets updated, and with the right permissions, that gets funnelled to the various actors. 
- [ ] Which solver results count as success? What residual thresholds and failure modes are acceptable?
--- All failures should be written down at the end of the simulation. 
--- Qualified successes should be written as successes, but their qualifications noted (e.g solution is asymptotic, solution is non-unique (list all solutions), etc.). An example would be matching pennies -- if the task is to find pure-strategy equilibrium, none exists; but if the task is to find mixed-strategy equilibrium, one exists. 
--- Failures that are inherent in the mathematical do not need to be fixed. For instance, if monopoly has positive constant demand at every price, then its profit is unbounded, the profit maximisation problem cannot be solved. The user should note this result. 
--- For failures that arise because of computation method (e.g high numerical instability, non-convergence, resource convergence), try another alternative method. If this fails, report the methods used, and report the failure. 
--- For coding errors, stop execution, diagnose, fix, re-run tests before executing again. No human-in-the-loop approval is needed before executing again. 
- [ ] Which economic models need exact analytic benchmarks before adding LLM actors?
--- Production actor trajectories use LLMs. Scripted/mathematical actors remain development fixtures; analytical benchmarks verify the separate mathematical benchmark path and mechanism correctness. 
- [ ] How will uncertain or LLM-assumed parameters be labeled and audited?
--- To be handled in future iterations. 
- [ ] What custom code is allowed in the first release, and who approves it?
--- To be handled in future iterations. 
- [ ] What isolation guarantees are required before external users can run generated experiments?
-- To be handled in future iterations. 

## 11. Instructions for the coding agent

**Do not implement the entire plan in one pass.** Start with Milestone 1. Before writing code, restate the component boundaries and identify unresolved decisions. Use `uv`, Pydantic v2, and tests. Keep the trusted runtime independent of experiment-specific logic. Prefer a working vertical slice over a large hierarchy of abstract classes. Do not invent empirical parameters or claim that synthetic LLM feedback predicts real consumers. Stop at the milestone boundary for human review.

## 12. Accepted decisions and implementation refinements (2026-10-31)

This readable plan takes precedence over the technical plan and interface sketch, particularly for milestone scope. The sketch is tentative. M1 is a working policy-driven payoff-matrix vertical slice; later interfaces are added only when needed.

### Actor execution and benchmarks

Production actor decisions use LLM policies. Mathematical solutions run separately on matching model assumptions and fresh state, as benchmarks. Report the LLM trajectory, benchmark solution concept, benchmark diagnostics, and deviations in actions and outcomes. Specify the compared round or aggregation explicitly; an LLM trajectory need not converge. Benchmark failure must not invalidate an otherwise successful actor run or be presented as proof of equilibrium nonexistence.

Information permissions are experiment-specific. Use textbook conventions when available; otherwise record explicit assumptions in configuration and list them at the end of the experiment. No approval gate is required merely to choose and disclose such defaults. Never present an assumption as calibrated evidence.

### State, decisions, permissions, and progression

WorldState contains public state and private state keyed by actor ID. Each private record contains facts and memory. An actor receives only its permitted public fields and its own permitted private fields/memory; another actor's private record is never supplied. Public state is immutable from the policy's perspective. Policy returns one action and an optional typed own-memory replacement; the runtime validates and commits it. M1 permits policy edits to memory only; richer edits to own private facts require an explicit typed contract later. No separate top-level memory store.

Pydantic frozen models are shallow: use deeply isolated snapshots at component boundaries and revalidate proposed values. An actor's mutation of its observation must not affect authoritative state, another observation, or earlier events. Trusted protocols declare explicit public/private field allowlists and build typed observations. Check projections and policy requirements independently. Available action kinds are derived solely from Actor.action_space in v1.

Protocol determines phase progression; runtime increments tick and atomically commits domain changes plus progression. Mechanism transition results contain domain public changes/outcomes, not authority to schedule actors. Future mechanisms needing private fact changes must declare a validated typed update contract. All simultaneous observations use the same pre-commit world. Validate exactly one action per active actor, ownership, schema, complete batches, state references, and finite outputs before commit.

Use JSON-compatible typed payloads immediately, reject unknown fields and nonfinite numbers, and use versioned component/schema IDs. M1 remains a local trusted-code runner, not an untrusted-code sandbox. No arbitrary imports or generated extensions.

### Canonical events and results

The internal event log is the canonical committed record: initialization plus ordered commit events containing actions, outcomes, and complete state snapshots in M1. Replay reconstructs states without calling policies, mechanisms, or LLMs. Validate event ordering and serialization. Full snapshots favor clarity over scale; deltas can come later. Internal logs contain private state and are restricted runtime artifacts, never actor observations. A future shared/exported view must redact private content. M1 guarantees in-memory atomic commits; durable crash recovery and tamper evidence are future work.

Distinguish completed runs, step limits, invalid actions/transitions, numerical failures, and mathematical conclusions. M1 reports completion/step limit in RunResult and raises validation errors for invalid runs without returning a partial successful result. Later solver reports include residuals, feasible bounds, solution concept, qualifications, method attempts, and bounded fallback budgets. Non-convergence is not proof of nonexistence; general enumeration of every equilibrium is not promised. Mixed-strategy representations and private-information payoff oracles need specialized future contracts. Defer DecisionContext.evaluate_candidate until rival-action assumptions and authorization are defined.

Record assumptions and selected component versions in M1; richer hashes, model-call provenance, RNG keys, and benchmark metadata arrive with their milestones. LLM reporting stores inputs, outputs, and optional concise rationales, not internal thought processes. Specify explicit seeded/keyed randomness before stochastic mechanisms or solvers.

### M1 acceptance and notebook

Implement a packaged two-player prisoner's dilemma with scripted A=cooperate and B=defect, a simultaneous protocol, registered move schema, payoff mechanism, trusted runtime, and replay. Expected payoffs: A=0, B=5. Support repeated scripted rounds to verify history and memory. Test action ownership/payloads, invalid batches, observations and private isolation, nested mutation, independent runs, transition validation, finite JSON values, evaluation purity, replay/serialization, termination and step limits. No solver or LLM integration in this milestone.

`visualisations/payoff_matrix.ipynb` must import and call the packaged example, show payoff matrix, actual actions/payoffs, committed trajectory/replay, and end with configured assumptions. Notebook cells do not duplicate the runtime or mechanism. Execute the notebook as an acceptance check.

### Contradiction register and resolutions

- Technical M1 includes broad interfaces/registry while readable M1 prioritizes a working slice: implement only the registry/contracts needed by M1. Later economic/solver/experiment milestone order follows the readable plan.
- Technical plan recommends configuration-generating LLMs first; readable plan prioritizes actor LLMs after controlled fixtures: follow the readable milestones; no requirement to build a compiler before actor policies.
- Solver-driven examples previously described the experiment's primary outcome: retain as separate benchmark runs; LLM outcomes take precedence.
- Readable section 10 said no analytic benchmarks because all actors are LLMs, conflicting with the opening and milestones: benchmarks verify models and the separate solver path; they do not replace production LLM actors.
- Interface/technical text had top-level memory and initial_memory: superseded by private[actor_id].memory and typed Decision memory proposals.
- Protocol owned scheduling but mechanism owned complete next_state: protocol chooses phase, runtime commits tick/phase with mechanism domain changes.
- Observation carried a second list of allowed actions despite fixed actor action spaces: derive it from the actor definition.
- Technical approval gates for every invented parameter conflicted with experiment defaults: record defaults as assumptions; approval requirements for deployment of untrusted extensions remain a future milestone.
- Technical instructions required copying the whole sketch; readable instructions reject a large unused hierarchy: implement contracts incrementally.
- Plan minimum Python 3.12 differs from repository minimum 3.13: retain repository >=3.13.
- Technical example tree places source under src; readable tree is illustrative: use src layout with simulation_core, components, and examples packages.
- A "frozen" model with dictionaries was described as immutable: isolation plus revalidation supplies execution-boundary protection; no claim of deeply frozen Python objects.
- Solver success booleans cannot express all requested mathematical qualifications: specialize the result contract when the benchmark milestone begins.

## 13. M1 generality requirements and implemented contract refinement

This section supersedes earlier M1 descriptions where they differ. The toolkit foundation must generalize across experiments before M2. Shared
Policy, Mechanism, and ProtocolRules are explicit abstract parents; concrete
components inherit them and pass static type checks. Mechanism includes separate
config, state, and action validation hooks. Runtime and shared models contain no
payoff-matrix labels, actor counts, action labels, or public field names.

A SimulationConfig declares protocol parameters and per-actor observation/write
permissions; actors declare policy parameters. Registered factories create fresh
components per run and fresh policies per actor. The registry exposes an inventory
of approved IDs plus action/parameter JSON schemas for a simulation-creating agent.
Experiment definitions are serialized configs, not modifications to runtime.

Observation construction belongs to the trusted core and reads configured
permissions independently of protocol code. Remove the redundant observe/project
pair from the scheduling interface; protocols cannot provide an actor observation.
Allow only configured public and own-private fields. Permissions select top-level
fields, including their nested contents. Missing permissions expose no public or
private facts; own memory read/write defaults remain enabled. Policy private fact
updates patch only explicitly writable own fields; memory replacement is separately
controlled. Mechanism proposals can replace configured actors' private records;
reject conflicts with policy updates to the same record instead of silently
choosing a writer. Public state and scheduling remain immutable to actors.

Outcome permits empty or partial actor payoffs and arbitrary typed JSON metrics.
Validate unknown actor references centrally; let each mechanism decide whether a
particular phase/model requires complete payoffs. Validate mechanism-specific state
invariants on initialization and every proposed commit, in addition to core checks.

Normal-form games use explicit profile/payoff cells and per-actor finite choice
sets, supporting arbitrary IDs, actor counts, asymmetric choices, and configured
history/payoff field names. Prisoner's-dilemma labels, payoffs, scripts, permissions,
and assumptions live only in its JSON config. Simultaneous protocol and scripted
policy have no experiment field names. A separate action-recording mechanism and
numeric measurement config prove that non-game outcomes run through the same loop.

Acceptance adds: declarative config round trips; registry schema discovery;
abstract contract enforcement and mypy; asymmetric three-player game; numeric
recording with no payoffs; runtime-owned projection despite a protocol defining an
unused observe method; denied private/memory writes; private update conflicts;
active-actor subsets; and fresh policy instances. Re-execute the notebook with both
fixtures and retain the original payoff visualization and canonical replay checks.
This is a refinement of M1, not advancement to the economic/solver milestone.

## 14. Requests, resolved specifications, provenance, and temporary jobs

User input and execution configuration are separate Pydantic contracts.
`ExperimentRequest` accepts an incomplete hypothesis, supplied inputs, and explicit
requirements. `SuppliedInput` records a name, JSON-compatible value, optional source
reference, and optional target JSON Pointer. The simulation-creating agent resolves
this request into `SimulationConfig` using registered components. This revision
implements the data contracts, not a natural-language compiler. Unmapped inputs and
free-text requirements still require agent interpretation; only explicitly mapped
input values can be mechanically checked against the resolved specification.

`SimulationConfig` is the complete execution specification. Shared fields are typed
by Pydantic; extensible component parameter sections are validated against their
registered Pydantic schemas, and mechanisms validate cross-field/domain constraints.
The registry exposes request/config schemas as well as component parameter/action
schemas. Do not generate a new Python schema class for every job when a registered
contract already expresses its requirements.

Assumptions are structured Pydantic records: configuration JSON Pointer, resolved
value, source (`user`, `textbook`, `model`, or `default`), rationale, and optional
reference. The source describes provenance, not evidential reliability. A user may
explicitly supply an assumption; default/model values must not be described as
calibrated observations. References, if supplied, must be real; validation does not
independently verify external citations. Validate that paths exist and values match
the resolved config. Reject duplicate assumption paths and assumptions referring to
other assumptions. A configuration change must update affected assumptions rather
than leave stale provenance. Not every field is necessarily an assumption.

`JobManifest` binds request to resolved simulation and verifies mapped supplied
inputs are preserved. `JobRunner` validates before creating a temporary per-job
directory, writes a versioned JSON manifest, executes through `ExecutionBackend`,
and removes job files on success or exception. The returned `JobResult` contains
the original request, resolved config, assumptions, results, and canonical events
in memory and can be explicitly exported by the caller. The runner does not write
a persistent result or config. Checked-in JSON examples are regression fixtures,
not accumulating job outputs. Full returned artifacts contain private data and
must remain restricted to authorized users.

`LocalBackend` uses the preinstalled trusted registry and runtime. It provides no
process/container security isolation. Later isolated workers should preinstall the
trusted core/component library; receive a manifest selecting IDs and parameters;
and only receive an extra code bundle when a genuinely new extension is required.
The coding agent selects one protocol and mechanism per simulation (each can
compose phases/submodels), plus one policy implementation/configuration per actor.
The registry creates distinct policy instances even when actors share a policy ID.
RecordingMechanism is an alternative to PayoffMatrixMechanism, not mandatory event
logging infrastructure. The runtime records canonical events for every mechanism.

The notebook and example entrypoints use the temporary job path. Tests cover
incomplete requests, request/config round trips, mapped input preservation,
assumption pointer/value consistency, invalid sources, parameter preflight,
cleanup after success/failure, and retained provenance/replay after file deletion.

## 15. Accepted Milestone 2 first increment — LLM actors with a finite-game benchmark

Accepted and implemented for offline execution, with an opt-in live adapter/test. This
M2.1 precedes the original continuous-economic/numerical-solver work (M2.2). M3–M7
retain their existing scope. This puts LLM behavior first while reusing the normal-
form experiment to verify the separate benchmark architecture before adding demand
models or numerical optimization.

Deliverables:

1. General `LLMPolicy` using a typed model-gateway interface. It receives only the
   actor observation, actor-specific configured instructions/persona, and the action
   response schema. It returns the same Decision contract as other policies. Log
   bounded request/response metadata and optional concise rationale; validate
   structured responses and enforce bounded retries/call budgets. Keep credentials
   outside actor configuration, manifests, and extensions. A deterministic fake
   gateway supplies ordinary tests. Any provider adapter/live smoke test is explicit
   integration work; no credentials are assumed to exist.
2. A separate Solver/GameView contract and finite normal-form pure-Nash benchmark
   implementation. Enumerate legal profiles through Mechanism.evaluate, identify
   best-response conditions, and report all pure equilibria for this bounded finite
   domain. Enforce a profile-count budget. Distinguish solved, multiple solutions,
   no pure equilibrium, and budget exhaustion. Absence of a pure equilibrium is not
   absence of mixed equilibria; mixed-strategy solving is out of M2.1 scope.
3. BenchmarkRunner operates on a fresh matching model and never substitutes solver
   actions into the LLM trajectory. Benchmark failure does not invalidate a completed
   actor run. Compare a configured round (initially the final committed round),
   report payoff deltas to each equilibrium or an explicitly identified selected
   equilibrium, joint-action differences, and unilateral deviation gains (regrets).
   Never silently average/select equilibria or call an LLM outcome an equilibrium.
4. Extend the request/resolved-spec/job-result contracts with explicit benchmark
   selection, comparison rule, diagnostics, and model-call provenance. Preserve
   existing temporary-file cleanup and canonical state replay semantics.
5. Update the notebook to show primary LLM outcomes alongside the benchmark and
   deviations. Clearly label deterministic fake-gateway runs versus live model runs.

Acceptance:

- Existing scripted experiments and replay pass with the same core execution loop.
- Fake-gateway integration exercises actual LLMPolicy prompts/response validation,
  private-state isolation, memory handling, malformed responses, retry limits,
  budgets, and deterministic recorded replay without model recalls.
- Prisoner's dilemma has the unique pure equilibrium (defect, defect), payoffs
  (1, 1). A scripted/fake profile (cooperate, defect) produces payoff deltas (-1, +4)
  and unilateral regrets (1, 0) against that benchmark.
- Matching pennies reports no pure equilibrium; a coordination game reports multiple
  pure equilibria; a profile-budget limit reports an incomplete benchmark, not an
  equilibrium/nonexistence conclusion.
- Benchmark evaluation leaves actor state, memory, events, and inputs unchanged.
- Comparison output retains the exact model/config and solution concept used;
  numerical or unavailable benchmarks are reported separately from actor status.

Full untrusted-code/container isolation remains M6. Trusted local LLM adapters may
be exercised before then, with explicit budgets; do not execute generated Python in
LocalBackend. M2.2 then adds linear demand, costs/payoffs, analytical benchmarks,
and continuous numerical equilibrium search using the same benchmark contracts.


## 16. M2.1 implementation and verification status

Implemented generic LLMPolicy, ModelGateway/ModelRequest/ModelResponse contracts,
FakeGateway, shared per-job BoundedGateway, and an OpenAI Responses transport.
The generic policy has no game-specific action names, payoff formulas, or world
access. Runtime injects only the actor's declared action payload schemas. Response
schemas constrain identity/kind/payload; JSONEntry lists carry generic private
updates using JSON-encoded values. Observation includes own write permissions.
Schema/JSON failures and disallowed writes receive bounded retries; runtime still
independently enforces domain legality, schemas, identity, and permissions before
commit. Domain-invalid actions that satisfy a broad payload schema are rejected
by mechanism action validation rather than silently committed.

Actor policies retain only bounded call diagnostics, not a hidden conversation.
Their next prompt uses committed private memory. ModelCallRecord stores fake/live
mode, requested and resolved model IDs, permitted request contents, response,
request ID, token usage, status, and error category. Each commit Event records calls
for that batch; RunResult aggregates them. On failure LLMPolicyError exposes the
failing policy's bounded records; no incomplete batch is committed. Full diagnostics
are internal/private artifacts. No hidden reasoning is requested.

Gateway budgets limit calls, output tokens per call, and request/response sizes.
These limits do not estimate a dollar cost. The live transport uses an allowlist,
timeout, bounded HTTP reads, sanitized errors, strict response schemas, and no
transport retries. Credentials remain in a trusted gateway object and are read
from OPENAI_API_KEY, never actor configuration or manifests. OPENAI_MODEL or an
explicit argument chooses the model; no live model is assumed. Keys and model
access have not been tested until provided. The default notebook/test suite makes
zero live API calls. Ordinary provider tests use mocked HTTP responses.

Solver and GameView are abstract parents. PureNashSolver exhaustively evaluates
bounded finite profiles through GameView and reuses cached payoffs for unilateral
checks. It returns every equilibrium within the declared payoff tolerance, multiple
solutions, no pure equilibrium, or budget exhaustion. NormalFormGameView owns
isolated config/state snapshots and delegates payoffs to the selected mechanism.
Normal-form validation checks unique legal profile coverage without materializing
an extra Cartesian product of possible profiles.

BenchmarkSpec declares solver/view/parameters, complete-information assumption, and
compared tick (final by default). LocalBackend runs BenchmarkRunner after the
primary actor simulation. The benchmark uses a copy of the compared round's
precommit state and never modifies actor events/actions. BenchmarkReport includes
all equilibrium comparisons, payoff deltas, action differences, unilateral regrets,
and SHA-256 of the resolved configuration. Expected numerical/adapter failures
produce a failed benchmark alongside the completed actor result; programming errors
propagate for diagnosis rather than being silently swallowed.

The notebook imports examples.llm_payoff_matrix, runs generic LLMPolicy through the
fake gateway by default, shows the configured game, actor outcomes, separate Nash
benchmark, deviations, call metadata, replay, and structured assumptions. Its
USE_LIVE_API flag explicitly enables run_live_job after key/model configuration.
Saved fake results: cooperate/defect, payoffs (0,5); pure Nash defect/defect, (1,1);
deltas (-1,+4); regrets (1,0). These fixed fake results are integration fixtures,
not observed behavior of an LLM or a human population.

Next implementation boundary is M2.2 (continuous economic evaluation and numerical
benchmarks), after live M2.1 verification when credentials are available. Untrusted
code/container isolation remains M6 and is not supplied by a model gateway.


## 17. Required per-action rationale and live Meta verification

LLM responses now require a concise nonempty stated rationale with every action.
Blank/null/missing rationales are schema failures and consume bounded attempts.
These are decision explanations, not private internal reasoning. Decision carries
the rationale; Event stores the complete committed decisions; accepted call records
retain the same rationale. Replay checks trace/action/rationale consistency. The
runtime emits one JSON log record per committed action; stream_action_trace enables
console output, and the notebook displays every turn's action and stated explanation.
Scripted policies explicitly label their deterministic configured behavior.

Host-only LiveModelSettings loads API_KEY and MODEL from .env (standard OpenAI
aliases remain supported), including from a notebook subdirectory. Credentials are
SecretStr fields excluded from serialization. Explicit environment wins over file
values. Muse models use Meta's documented Responses endpoint; the shared generic
policy contract does not change. The example records low reasoning effort for Muse
and retains existing request/call/output budgets. No API key enters job artifacts.

Live verification completed with muse-spark-1.3-contributor: two first-attempt
accepted calls; A=defect and B=defect; payoffs (1,1); benchmark deltas (0,0), regrets
(0,0). Both stated that defect strictly dominates regardless of the unknown rival
choice. Saved notebook outputs include that live run and its decision explanations.
The previous fake example A=cooperate/B=defect was hardcoded test data, not live
model behavior. Notebook USE_LIVE_API=True now incurs calls on re-execution;
False retains the deterministic offline fixture. This single live run demonstrates
integration, not calibrated human behavior or a guarantee of future identical choices.

## 18. M2.2 first increment — textbook homogeneous Bertrand

User scope supersedes the earlier suggestion to begin with differentiated demand.
Implement homogeneous goods first; differentiated Bertrand is deferred. Two LLM
firms set prices simultaneously; q_i=Q(p_i) below rival price, Q(p_i)/2 at an exact
tie, and zero above it, where Q(P)=max(a-bP,0). Identical constant marginal cost,
unlimited capacity, no fixed costs, complete information, and one round form the
default textbook example. Default a=100, b=1, c=20, price domain [0,100] are recorded
illustrative assumptions. Prices are continuous with no cents grid or tie epsilon.
LLMs receive the piecewise function and parameters; the benchmark solution is not
included in their observation. Current rival prices remain hidden until commit.

General economic parents: DemandModel (aggregate demand at one market price),
CostModel, ProfitModel, and AllocationRule. Implement LinearDemand,
ConstantMarginalCost, RevenueMinusCost, and exact LowestPriceAllocation; compose
these in HomogeneousBertrandMechanism. Enforce finite/nonnegative prices and
quantities, actor references, price bounds, allocation conservation, history and
outcome invariants. The mechanism supports arbitrary IDs and multiple firms;
its two-firm example uses a typed BertrandExampleSettings builder. Core runtime
and generic LLMPolicy remain independent of the experiment.

Generalize GameView into a payoff view, FiniteGameView for enumerable actions,
and BestResponseGameView for continuous unilateral optimization. A best response
may report an unattained payoff supremum with no maximizing action plus a feasible
witness. Do not silently use a price grid, minimum price decrement, or smooth solver
at the discontinuous tie boundary. The shared deviation diagnostic belongs to the
game-theory benchmark layer, not the runtime or an individual experiment.

TextbookBertrandSolver certifies p_A=p_B=c only for two identical-cost firms with
feasible cost, room above it, and positive demand at cost. Reuse mechanism payoff
primitives and a region-wise continuous best-response oracle to check unilateral
gains. Report price bounds, payoff tolerance, theorem scope, and unsupported
assumptions explicitly. No finite profile count applies to a continuous benchmark.
Asymmetric costs or a price floor outside scope report unsupported without
invalidating a completed actor run or claiming nonexistence. Keep p=c distinct
from the monopoly/joint-profit maximum. Shared comparison records add numeric
action/metric differences and full best-response diagnostics.

Acceptance checks: undercut winner captures all demand; exact tie halves it;
demand is truncated at zero; below-cost sales lose money; own-price demand weakly
decreases (including the tie jump); prices/schema violations fail before transition;
configuration/state/evaluation remain isolated; p=c and q_i=(a-bc)/2 match across
parameters; no profitable unilateral deviation at the benchmark; above-cost rival
examples correctly distinguish attained monopoly best responses from unattained
undercutting limits; independent dense-grid checks lower-bound the analytic
supremum; arbitrary firm IDs/multifirm allocation; actor privacy and simultaneous
observations; per-action explanations, replay, and benchmark independence.

`visualisations/bertrand.ipynb` imports packaged code and compares actual LLM prices,
quantities/profits, and rationales with the mathematical equilibrium, alongside
piecewise demand plots, deviation qualifications, provenance, and assumptions.
Verify offline first, then use a bounded live run with the existing .env provider.
The existing finite-game notebook and the user's generic policy wording are preserved.


M2.2 homogeneous Bertrand completion: the notebook was verified offline and then
executed live with muse-spark-1.3-contributor. Both firms chose p=20, matching the
analytical benchmark; each supplied 40 units and earned zero profit. Both live
requests were accepted on the first attempt and retained a stated rationale.
The full suite passed 101 tests (one opt-in live pytest skipped); notebook live
execution was verified independently. Differentiated Bertrand remains deferred.

## 19. Differentiated Bertrand and typed user inputs

Implement the originally planned segmented-logit model with an outside option.
Each firm supplies its ID, constant marginal cost, feasible price interval, and
optional persona. Each segment supplies ID, population, positive price sensitivity,
and one utility for every firm, plus optional outside utility. The outside baseline
defaults to zero and must be recorded when omitted. Utilities and sensitivities must
use coherent units. At least two firms and one segment are supported, with arbitrary
IDs and firm-specific bounds. Inputs are Pydantic models and can round-trip through
JSON. Missing required numerics and inconsistent dimensions fail, not silently default.

The compiler maps supplied inputs to validated SimulationConfig paths, records them
in ExperimentRequest, and records assumptions and information permissions. The
notebook supplies clearly labeled illustrative numbers until the user replaces
them. Explicit per-firm permissions override default complete public information;
private observations remain own-actor only. A complete-information mathematical
benchmark is explicitly identified even if actor information is restricted.

DemandSystem and DifferentiableDemandSystem are reusable joint-price interfaces,
distinct from scalar aggregate DemandModel. SegmentedLogitDemand uses a stable
maximum-centered exponential calculation including the outside utility. Its result
validates per-segment probabilities and population conservation. The differentiated
mechanism composes demand, constant costs, and existing profit evaluation. It owns
the own-profit gradient; policies and solvers do not duplicate economic equations.
Price actions, protocol, LLMPolicy, event traces, and job cleanup are reused. Only a
general JSON-boundary validation fix is needed in the runtime: JSON-compatible
parameters/payloads are validated as JSON so strict tuple-backed schemas accept
transported arrays without weakening scalar validation.

DifferentiableScalarGameView supplies generic bounds, scalar actions, own-payoff
gradients, and numerical best responses. A generic NumericalNashSolver searches
multiple initial price profiles with bounded projected-gradient roots; verifies
candidate unilateral gains with uniform/geometric sampling and local peak
refinements plus independent SHGO; and attempts a bounded best-response fallback
when root search fails. Include boundaries in searches, preserve actual negative
profits where bounds force losses, impose objective budgets, and report boundary
flags. Retain all distinct candidates found. Never claim uniqueness or a rigorous
global maximum from numerical convergence. Both SolveResult and BestResponseResult
carry numerical-versus-analytic certification. Failed searches/budget exhaustion
remain separate from the primary actor result and do not prove nonexistence.

Acceptance includes: analytic equal-share/symmetric-price case; outside conservation;
positive demand for differentiated products at unequal prices; own/cross-price
response directions; utility translation invariance; finite extreme-utility outcomes;
derivative finite differences; malformed dimensions/nonfinite inputs; user input
preservation and default provenance; bounds and constrained equilibria; wide-bound
search robustness; independent dense-grid lower checks; multi-equilibrium generic
game and rejection of a stationary profit minimum; bounded fallback/failure/budgets;
private information, simultaneous observations, rationales, replay, and purity.

`visualisations/differentiated_bertrand.ipynb` contains an editable Pydantic input
cell and demonstrates the complete flow with the existing live provider. Numerical
charts use an explicitly chosen candidate index; tables retain all comparisons.
Verify offline before the bounded live run. No key is written to the notebook.

User's subsequent folder question is a layout review, not authorization to merge
files in this increment. Co-locating matching mechanism/view classes is reasonable,
while preserving their interfaces: mechanism owns consequences, view exposes a
read-only solver capability, and runtime owns execution. Individual run values,
information choices, and actor instructions remain configuration rather than
hardcoded mechanism implementation. Reusable demand/cost/profit models and generic
solvers/optimizers should stay reusable even if domain-specific files are co-located.


Differentiated implementation verification: 129 tests passed (one opt-in live
pytest skipped); mypy and Ruff passed. Both offline and live notebooks executed.
With illustrative inputs the live Contributor model chose prices (2.30,2.50),
compared with one numerical candidate (2.349056,2.528764). Candidate gains checked
around 1e-13; estimated LLM-profile unilateral gains were (0.328590,0.031705).
These are results for synthetic input values, not a uniqueness proof or empirical
forecast. Failed stationary points are retained in diagnostics. After an initial
incomplete response, the differentiated example records minimal reasoning effort
and a 4,000-output-token cap; sanitized incomplete reasons and usage are logged.
Only complete valid action batches commit. No earlier notebook is rerun or replaced.

## 20. Accepted component co-location and shared-building-block layout

Move NormalFormGameView, BertrandGameView, and DifferentiatedBertrandGameView into
their corresponding modules under components.mechanisms. Keep the classes and their
abstract contracts distinct; co-location does not give solvers commit authority.
Remove components.games and update imports. The trusted runtime owns the execution
loop; mechanisms own consequences and transition proposals; views expose isolated
payoff/optimization capabilities.

Group shared implementations under components.common.economics (economic model
primitives and segmented logit) and components.common.math (generic scalar numerical
optimization). These are reusable classes/models/algorithms, not an undifferentiated
collection of helper functions. Preserve the model-agnostic dependency direction:
math routines receive objectives/bounds and do not import market mechanisms or
actor policies. Game-level solution concepts remain in components.solvers; abstract
contracts remain in simulation_core. Per-run values, permissions, actor instructions,
and assumptions remain typed configuration. No component IDs or JSON contracts change.

Update source/tests/docs/notebook imports. Verify all tests, lint, types, and all
notebook code paths with fake gateways; preserve prior live notebook outputs and
make no new API calls for this structural refactor. Do not retain legacy import shims
for this internal package reorganization.
