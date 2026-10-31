# Composable Simulation Compiler — Implementation Plan

**Status:** Draft for human review, not an authorization to deploy.  
**Target:** Python 3.12+, `uv`, Pydantic v2, NumPy/SciPy for numerical economics.  
**Companion:** [`simulation_interfaces.py`](simulation_interfaces.py) — the authoritative *proposed* interface sketch. Split it at its `FILE:` markers before implementation.  
**Goal:** An LLM coding agent compiles natural-language hypotheses into validated simulations of strategic or behavioral actors. Support undergraduate microeconomics and turn-based market-feedback studies, including LLM-persona advertisement reception.

## 0. Decisions already made

1. **Actor owns its experiment-specific action space.** Do not model every hypothetical capability. In v1, an active actor may choose any action declared in its `Actor.action_space`. The protocol determines *when* actors act; not a second action permission list. A future phase-dependent action space is an explicit extension, not v1.
2. **Policy chooses actions.** Policies include optimizer-based, scripted, probabilistic, and LLM policies. Policies do not mutate world state and cannot read the entire world directly.
3. **Mechanism determines consequences.** Demand equations, costs, payoff equations, message delivery, and automatic state changes belong here. Compose smaller `DemandModel`, `CostModel`, and `PayoffModel` implementations inside mechanisms where useful.
4. **WorldConfig differs from WorldState.** WorldConfig contains fixed initial/exogenous conditions. WorldState contains evolving public/private variables, memory, current phase, pending actions. Actor identity/attributes are immutable; mutable actor state is in WorldState.
5. **Protocol governs scheduling and visibility.** It chooses active actors, creates their observations, validates action batches, and determines termination. It must not calculate payoffs or select actions.
6. **Experiment organizes runs.** One simulation is a valid use case; an ExperimentConfig optionally defines treatments, controls, repetitions, seeds, and outcome metrics.
7. **Solver is optional.** Solver-driven mode finds an equilibrium or optimum via read-only payoff evaluation. Policy-driven mode samples/collects actions directly. Both commit state only through the runtime.
8. **Runtime owns execution.** The LLM does not generate or modify the runtime's scheduling/commit loop. Runtime validates actions and proposed next states, logs events, and enforces step limits.
9. **Generated code is untrusted.** Default to declarative configuration and registered components. New custom code is an extension that must be validated and executed in an isolated worker. A `uv` environment is a dependency environment, **not** a security sandbox.

## 1. Scope and non-goals

**Minimum examples:** homogeneous Cournot, differentiated Bertrand, Stackelberg quantity leadership, monopoly, competitive market clearing, static/repeated normal-form games, and an LLM-persona advertisement A/B test. Add auctions and social diffusion after the first milestone.

**Non-goals for v1:** a universal game-theory solver, a guarantee of equilibrium existence/uniqueness, empirically validated human-behavior forecasts, unrestricted arbitrary code execution, and continuous-time simulations. Avoid claiming that synthetic LLM respondents are statistically equivalent to real survey participants.

**Success criterion:** Bertrand, Stackelberg, and advertising examples all run without editing `simulation_core/runtime.py`. Analytical benchmarks match expected solutions, and custom extensions cannot change the trusted controller's execution semantics.

## 2. Source tree and file boundaries

Split the companion Python file according to its `FILE:` headings:

```text
project/
  pyproject.toml
  uv.lock
  src/
    simulation_core/
      __init__.py
      types.py            # Actor, ActionSpace, Action, Observation,
                          # WorldConfig, WorldState, Outcome, result DTOs
      policy.py           # Policy, restricted DecisionContext
      mechanism.py        # Mechanism: pure evaluate, transition proposal
      protocol.py         # Protocol: scheduling, observation, termination
      solver.py           # Solver, read-only GameView
      experiment.py       # SimulationConfig, ExperimentConfig, Treatment,
                          # ExecutionMode, ExperimentEvaluator
      runtime.py          # Trusted runtime; single implementation
      registry.py         # Approved, versioned component resolution
      execution.py        # ExecutionBackend, ExperimentRunner
      validation.py       # Action/state/invariant checks
      logging.py          # Event log, run metadata
    components/
      policies/
        profit_maximizer.py
        llm_policy.py
        scripted.py
      mechanisms/
        linear_demand.py
        segmented_logit.py
        bertrand.py
        cournot.py
        normal_form.py
        ad_exposure.py
      protocols/
        simultaneous.py
        sequential.py
        repeated.py
      solvers/
        nash.py
        backward_induction.py
        market_clearing.py
    worker/
      main.py             # Worker entrypoint, no host secrets
    controller/
      launcher.py         # Launches and monitors isolated workers
      model_gateway.py    # Optional, scoped LLM request mediation
  experiments/
    bertrand.json
    stackelberg.json
    advertisement_ab.json
  tests/
    test_interfaces.py
    test_bertrand.py
    test_stackelberg.py
    test_advertisement.py
    test_isolation.py
  Dockerfile.worker
```

**Keep together:** Actor + ActionSpace + WorldConfig + WorldState + action/result DTOs in `types.py`; Policy + DecisionContext in `policy.py`; Solver + GameView in `solver.py`. **Separate:** runtime from protocols and mechanisms; controller from worker; concrete models from their abstract interfaces. Split `types.py` later only if it grows unwieldy.

## 3. Core data contracts

- **Actor:** immutable `id`, `kind`, persona/attributes, action-space schema references, policy ID. `ActionSpace.schemas` maps action kind to a registered Pydantic action-payload schema. Examples: `set_price` with `price >= 0`; `set_quantity` with `quantity >= 0`; `share` with a bounded message.
- **Action:** `actor_id`, `kind`, typed/validated payload. Validate against the actor's declared action space *and* protocol's active actor set. An actor cannot submit actions on behalf of another actor.
- **WorldConfig:** immutable actor definitions, exogenous model parameters, initial public/private state, initial memory. Validate unique actor IDs, finite parameters, legal initial values, and parameter dimensions.
- **WorldState:** authoritative tick/phase, public/private state, actor memory, pending actions. Never pass this object wholesale to LLM policies. Prefer immutable snapshots and explicit transition results.
- **Observation:** permitted view for a single actor, including current visible information, accessible memory, and currently available action kinds. Its fields are defined by a versioned observation schema. `Policy.required_observation_fields()` declares requirements; `Protocol.observe()` enforces permissions. Validation fails if required information is not legitimately available.
- **Policy:** `choose_action(observation, restricted_context) -> Action`. LLM policies must return schema-conforming actions and should propose memory changes through explicit actions or transition results; no hidden, unlogged conversation state.
- **Mechanism:** `evaluate(config, state, candidate_actions) -> Outcome` computes hypothetical payoffs/metrics without mutation. `transition(config, state, committed_actions) -> TransitionResult` proposes a new state and events. Keep both pure with respect to their inputs. For stochastic behavior, extend the contract with explicit keyed randomness or a deterministic scenario input before implementation.
- **Protocol:** `active_actor_ids`, `observe`, `validate_action_batch`, `is_terminal`. Simultaneous moves must be collected before any rival sees the current-round actions. Sequential moves can reveal committed earlier actions.
- **Solver:** `solve(GameView) -> SolveResult`; GameView exposes only authorized action spaces and a pure payoff oracle. Record convergence, residuals, feasible bounds, and solution concept. **Do not silently commit failed equilibrium candidates.**
- **Runtime:** resolves registered components, initializes state, validates observations/actions, invokes policies or solver, validates proposed transitions, commits them, logs events, and stops on termination or resource limits.
- **Experiment:** base SimulationConfig plus treatment overrides, metric IDs, repetitions, seeds, and aggregation. Treatment overrides must be typed, allowlisted paths; arbitrary Python expressions are forbidden.

**Open design item for review:** The reference file's `JSONValue = Any` is a placeholder for JSON-compatible payloads. Tighten to a recursive JSON type or schema-validated Pydantic models in production. Define explicit state invariants and a clear versioning strategy for all schema IDs.

## 4. Ownership rules (anti-bleed checklist)

| Question | Sole owner | Explicitly not responsible |
|---|---|---|
| What actions can this actor take in this simulation? | Actor.action_space | Policy, solver |
| Which actor acts now? | Protocol | Actor, mechanism |
| What information may the actor see? | Protocol / observation projection | Policy |
| Which action is preferred? | Policy | Mechanism |
| What does a candidate action profile imply? | Mechanism.evaluate | Solver's own economic equations |
| Which profile satisfies Nash/backward induction? | Solver | Mechanism |
| What state change follows committed actions? | Mechanism.transition | Policy |
| Who validates and commits that state change? | Runtime | Mechanism |
| Which treatment and outcomes are tested? | Experiment | Protocol |
| How is untrusted code isolated? | ExecutionBackend / controller | Experiment-specific economic classes |

Avoid hidden duplication: a generic profit-maximizing policy must call an authorized payoff oracle rather than copy demand equations; solvers reuse mechanism evaluation rather than recreate payoffs; observations are not constructed by policies.

## 5. Execution semantics

### 5.1 Policy-driven (e.g., LLM ad test)

1. Validate SimulationConfig and resolve component IDs.
2. Initialize WorldState and event log.
3. While protocol is not terminal and step budget remains:
   - Ask protocol for active actor IDs.
   - Build permitted observations; verify policy input requirements.
   - Call each active actor's policy with observation and restricted DecisionContext.
   - Validate action ownership, payload, and batch completeness.
   - Ask mechanism for TransitionResult; validate state invariants.
   - Commit new state and append events atomically.
4. Return RunResult with state, outcomes, logs, and diagnostics.

For simultaneous phases, all policies observe the **same pre-commit state**. Their actions are held until the complete batch is ready. The runtime must not reveal partially collected actions.

### 5.2 Solver-driven (e.g., Bertrand Nash)

1. Build a read-only GameView from the current world, mechanism, protocol, and solution concept.
2. Solver calls the mechanism's **pure** `evaluate` through GameView many times to compare candidate profiles.
3. Solver returns a candidate action profile and diagnostics; runtime checks action legality and convergence/residual tolerances.
4. If acceptable, runtime calls mechanism `transition` **once** to commit; otherwise report failure or an explicitly configured fallback (never silently treat failure as equilibrium).
5. Advance protocol state and record results.

**Stackelberg caution:** A backward-induction solver computes the follower response hypothetically while choosing the leader's commitment. That is not equivalent to running an arbitrary two-turn heuristic. A behavioral sequential Stackelberg *simulation* may commit leader and follower actions on separate turns, but it must not be labeled a subgame-perfect equilibrium unless the corresponding solution concept has actually been solved.

## 6. Test cases and acceptance criteria

### Test A — Bertrand with segmented logit

Two firms, three customer segments. Each segment has population `N_g`, price sensitivity `alpha_g > 0`, and baseline utilities `v_ig`. Include an outside option:

\[
P_{ig} = \frac{\exp(v_{ig}-\alpha_g p_i)}{1+\sum_j\exp(v_{jg}-\alpha_g p_j)},\qquad
Q_i=\sum_g N_gP_{ig}
\]

Profit: `pi_i = (p_i - mc_i) Q_i`. `SegmentedLogitMechanism.evaluate` computes demand/payoffs. `NashSolver` searches for mutual best responses over a declared feasible price domain. The experiment changes Firm A's quality/utility input and compares equilibria.

**Assertions:** finite, nonnegative quantities; sum of firm demand <= total population; own-price demand decreases; cross-price demand increases; no committed changes during solver queries; reported best-response residual below tolerance or explicit failure. Use stable log-sum-exp to avoid overflow. Utilities and prices must use coherent units.

### Test B — Cournot and Stackelberg

Use `P(Q) = a - bQ`, `a > c >= 0`, `b > 0`, and nonnegative quantity actions. For identical `n`-firm Cournot with constant marginal cost `c`, compare computed equilibrium against:

\[
q_i^* = \frac{a-c}{b(n+1)},\quad
P^* = c + \frac{a-c}{n+1}
\]

For two-firm Stackelberg with identical constant costs and interior solution, verify leader and follower quantities against analytical backward-induction benchmarks. Ensure follower's observation contains the leader's committed quantity in a behavioral run; in equilibrium solving, ensure the leader anticipates the follower's best-response function. Add monopoly and competitive benchmarks without changing the runtime.

### Test C — Normal-form/repeated game

Implement payoff matrix mechanism and simultaneous protocol. Test prisoner's dilemma and a repeated version with persistent action history. Validate that current simultaneous actions are hidden until commit, while past actions become visible according to the observation schema.

### Test D — Advertisement reception

Actors: 2–3 consumer persona groups with heterogeneous attributes. Policies: LLM response or deterministic scripted test doubles. World: advertisement, prior exposures, private memory, optionally social links. Mechanism: expose ad, record responses, deliver shares. Protocol: baseline -> exposure -> discussion (optional) -> response. Experiment: ad A vs B, repetitions and seeded treatment assignment.

**Assertions:** each actor sees only assigned treatment and permitted messages; responses satisfy Pydantic schema; same scripted policy/seed gives reproducible logs; malformed LLM responses are rejected or retried within a fixed budget. Do not claim synthetic outcomes are calibrated human response rates.

### Test E — Security and robustness

Reject unregistered action kinds, unauthorized observation fields, invalid state transitions, duplicate actor IDs, nonfinite numerical outputs, malformed generated modules, worker timeout, memory overrun, and oversized stdout. Verify that worker code cannot access host secrets or unrestricted network resources. Include fuzz/property-based tests for invariants.

## 7. Coding-agent workflow and review gates

1. **Interpret request:** extract hypothesis, actors, actions, timing, information structure, mechanisms, solution concept, outcomes, and uncertain parameters.
2. **Compile specification:** prefer existing registered components. Emit typed JSON/Pydantic config, not new code when possible.
3. **Identify missing pieces:** if no component supports a requirement, generate a narrowly scoped subclass implementing a specific interface. Do not edit trusted runtime, registry policy, or controller.
4. **Validate:** Pydantic schema checks, static/interface checks, tests, mathematical invariants, dependency allowlist, resource budget.
5. **Human review gate:** surface all LLM-invented parameters, behavioral assumptions, information rules, model selection, and any new generated code. Require approval for scientific claims or deployment of untrusted extensions.
6. **Execute:** run through the selected backend; capture versioned config, component hashes, seed, solver diagnostics, events, outputs.
7. **Report:** distinguish theoretical results, synthetic scenarios, calibrated results, and externally validated predictions. Surface failed convergence, sensitivity to assumptions, and limitations.

## 8. `uv` setup

Use `uv` for dependency resolution and execution; **do not use pip**.

```bash
uv init --package simulation-platform --python 3.12
cd simulation-platform
uv add 'pydantic>=2,<3' 'numpy>=2,<3' 'scipy>=1.14,<2'
uv add --dev pytest hypothesis ruff mypy
uv lock
uv sync --locked
uv run pytest
uv run ruff check .
```

Use a `src/` layout and declare the project as a package in `pyproject.toml`. Pin and review `uv.lock`. For the worker image, install `uv` in a pinned/versioned manner and use `uv sync --frozen --no-dev` during image build; avoid runtime package installation from generated code. Keep optional LLM SDK dependencies in a separate extra/group when possible. If using `uv run` in a local development worker, it must not be confused with a security sandbox.

## 9. Isolated execution backend

**Development:** `LocalBackend` executes trusted, reviewed components directly for fast tests. Never use it for arbitrary LLM-generated Python.

**Untrusted extensions:** `DockerBackend` or stronger isolated worker. The host controller validates job manifest, allocates job ID and resource budget, mounts a read-only input directory, launches a fresh worker, captures bounded structured output, and tears it down. Worker runs the simulation framework plus job extensions. The controller must not import untrusted extensions into its own process.

Recommended restrictions: no network by default, non-root user, read-only root filesystem, no added Linux capabilities, no privilege escalation, CPU/memory/process/time limits, restrictive syscall policy, no Docker socket mount, minimal mounted paths, per-job isolation. Harden further (e.g., microVM) for hostile multi-tenant use. A Docker container is a practical boundary but not a formal guarantee against kernel-level compromise.

**LLM policies:** Since network access is blocked, a worker sends bounded structured model requests through a controlled IPC/gateway to the host, which enforces credentials, quotas, model allowlists, and logs. Do not expose API keys to generated code. The gateway is an explicit future milestone; use scripted policies for initial end-to-end tests.

**Worker protocol:** input = versioned JSON job manifest + read-only code/config bundle; output = bounded JSON result + diagnostics + event log artifact. Include job status, error categories, resource usage, and schema/component versions. Controller should use explicit container lifecycle cleanup; timing out a Docker client subprocess alone is insufficient.

## 10. Implementation milestones

| Milestone | Deliverable | Review/acceptance gate |
|---|---|---|
| M1 | Typed interfaces, registry, validators, pure runtime | Unit tests for action/state/observation boundaries |
| M2 | Linear demand, segmented logit, Bertrand/Cournot mechanisms | Demand invariants + analytical benchmarks |
| M3 | Simultaneous/sequential protocols; Nash/backward-induction solvers | Correct equilibrium diagnostics; Stackelberg test |
| M4 | ExperimentRunner, treatment overrides, metrics, event logs | Repeatable baseline/treatment comparisons |
| M5 | Scripted + LLM policies, ad-exposure mechanism | Schema-safe behavior; no information leakage |
| M6 | Isolated Docker worker + controller + model gateway | Security/timeout/resource tests |
| M7 | Coding agent: natural language -> registered spec -> reviewed extension | Same runtime supports all core examples |

**Recommended build order:** Start M1–M3 without LLMs. The first LLM feature should be configuration generation against a registry, not arbitrary code generation.

## 11. Open questions for human review

1. **State model:** Is a single immutable WorldState snapshot enough, or should larger simulations use event sourcing and partial state updates?
2. **Information and beliefs:** How should private types, beliefs, and Bayesian game distributions be represented? The v1 `GameView` is primarily for complete-information games.
3. **Optimization assumptions:** How does a `ProfitMaximisingPolicy` access authorized counterfactual payoffs in games with private information? Define objective, beliefs, and oracle permissions explicitly.
4. **Stochastic mechanisms:** Finalize explicit RNG/keyed draw contract; ensure hypothetical solver calls never advance global RNG state.
5. **Equilibrium multiplicity:** Which equilibrium selection rules, convergence tolerances, and failure policies are acceptable?
6. **Dynamic action spaces:** Is a fixed action space per actor adequate for all near-term protocols? Keep v1 simple unless auction phases require more.
7. **Parameter calibration:** Which user-provided data or external evidence can justify behavioral parameters? How should LLM-estimated assumptions be labeled?
8. **Security model:** Is Docker isolation sufficient for the intended users and threat model, or is a microVM service required?
9. **Extension API:** Should generated components be Python subclasses, declarative expressions, or both? Prefer declarative whenever possible.
10. **Schema strictness:** Replace placeholder JSON-compatible `Any` values with recursive JSON types and versioned schemas before production.

## 12. Coding agent instruction

**Implement in milestones. Do not silently modify the architectural contracts.** First split `simulation_interfaces.py` at the marked boundaries and make the package importable. Replace placeholders only with reviewed, typed implementations. Write tests before adding new economic models. Keep `SimulationRuntime` experiment-agnostic. Prefer `uv run`/`uv sync`, never `pip`. Treat scientific assumptions as explicit configuration and generated Python as untrusted. When a design decision is unresolved, document it and request human review rather than inventing hidden defaults.
