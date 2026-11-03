# Working in this repository

Build a small, general toolkit that external coding agents can compose for unfamiliar
simulations. LLM policies supply the primary actor decisions; mathematical solutions
are separately scoped references or validation checks. Keep domain rules out of the
trusted runtime and parent interfaces.

## Read first

- `docs/single_pass_authoring.md`: default complete-candidate workflow and `author-check`.
- `prompts/muse_coding_agent.md`: active instructions for the headless Muse Code worker.
- `prompts/external_coding_agent.md`: general extension-development SOP.
- `src/agent_tools/guide.py`: generated interface guide and starter entry point.
- The current user request and its files. Resolve material contradictions with the user;
  record ordinary modeling assumptions explicitly in configuration and the final report.

User instructions take precedence over this file. Do not start a live API run unless
the user has authorized it. When a live run is requested, carry it through validation,
execution, artifact review and a candid report of results and bottlenecks.

## Development and validation

- Use `uv` and the locked project environment; use `rg` for searches.
- Run Ruff, mypy and tests appropriate to the change. Prefer meaningful rejection,
  conservation, boundary, privacy and independently calculated reference cases.
- Do not import or execute generated experiment code on the host. Treat it as data;
  execute it and its tests in the isolated Docker worker.
- Author a complete candidate in one continuous pass. Use executable synthetic starters
  and `author-check`; repair named failures while retaining passing work. The staged
  plan/implementation route is explicit compatibility mode.
- Preserve existing uncommitted work. Never overwrite a sealed experiment version;
  create another version and retain provenance. Do not commit or publish unless asked.
- Do not add model-turn or generation-token ceilings by default. Keep coding-agent
  reasoning at the user-selected maximum. Timing targets are goals to measure.

## Components and information

- Reuse registered policies, protocols, mechanisms, recording and reporting helpers
  when their actual contracts match. Check dimensions, feasible sets, timing,
  information access and mathematical prerequisites before selecting a component.
- Put missing experiment rules, schemas, policies and checks in
  `experimental_components/<experiment_id>/<version>/`, outside `src`.
- Use native Pydantic models for configuration; do not embed configuration documents
  as JSON strings inside model fields.
- Protocols schedule actors. Mechanisms validate physical/economic legality and own
  transitions. Policies receive filtered observations and return one structured action
  per active actor per turn. Distinct phases may activate the same actor again.
- World state contains public facts and owner-specific private facts/memory. Never
  expose another actor's private state, private instructions or uncommitted action.
  Targeted messages must reach only their intended recipients unless explicitly public.
- Committed events are the canonical state record. Resume through checkpoints and the
  current-run response ledger; retain successful pending decisions instead of querying
  them again. Report unknown provider outcomes rather than silently duplicating calls.

## Models, credentials and isolation

- Coding uses headless Muse Code with `MODEL_CODING` and maximum reasoning.
  Simulation actors use `MODEL`.
- `.env` and all key values stay private. Never print them or include them in prompts,
  manifests, notebooks, receipts, source bundles or version control.
- The host discovers `API_KEY` plus any numbered `API_KEY_2`, `API_KEY_3`, etc.,
  deduplicates them and leases credentials for actor requests. Do not hardcode a key count.
- Each new experiment gets a fresh authoring session and input/workspace/home volumes.
  Do not mount or supply past experiment bundles, outputs, logs, private tests, host home,
  `.env` or Git history. Preserve context within the current experiment's session.
- Verify the authoring image, initial context and active mounts before relying on a
  blind trial. Actor calls go through the host relay; validation/report workers remain
  network-isolated and receive no provider credentials.

## Artifacts and reporting

- Preserve request resolution, assumptions, component specifications, tests, sealed
  source, execution settings, validation receipts, events, results and timing evidence.
- A notebook calls external code and uses recorded results. Organize it into background
  and rationale; execution/results/figures/reference comparison; decision rationales;
  assumptions in prose; and limitations. Show each decision/rationale once.
- Pre-execution previews contain rules, calculated theory and limitations, with observed
  behavior pending. Never invent LLM results or explain performance before it is observed.
- After live execution, repair presentation from saved results without another actor run.
  Keep scientific code and data unchanged for report-only repairs.
- Match comparison units: round payoff, cumulative payoff and final inventory/wealth
  are different measures. State benchmark assumptions and distinguish an alternative
  trajectory from a feasible unilateral deviation or an equilibrium claim.
- Record authoring, checking, actor/round, credential-wait and rendering timings. Report
  actual elapsed time and failures, including operator interventions; do not claim a
  speed target or general behavioral finding from insufficient evidence.
