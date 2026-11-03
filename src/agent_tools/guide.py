"""Small, current interface map and domain-neutral authoring starter."""

import inspect
from pathlib import Path

from components.library import standard_registry
from simulation_core.mechanism import Mechanism
from simulation_core.policy import Policy
from simulation_core.protocol import ProtocolRules
from simulation_core.solver import GameView, Solver

GUIDE = """# Authoring entry point

Start here, then read task.json and the response schema. You do not need to read
worker transport/assembly internals. Sources remain available for unresolved details.

## Select the route and identify gaps
- A pure calculation uses a callable and tests. Do not add actors or a solver wrapper.
- An interaction uses existing LLMPolicy + protocol + Mechanism + runtime.
- Reuse a mechanism only when its actual rules match; a similar action shape is insufficient.
- Select existing components below. For each missing rule, payload, timing or mathematical
  capability, record EXTEND with the relevant parent. Unsupported/unknown guarantees
  must remain explicit. Missing inventory entries are unknown, not compatible by default.
- Scalar interval search does not solve coupled vector constraints or certify convexity.
- A point reference can be a plain function; only implement Solver/GameView for solver APIs.

## Responsibilities and data flow
SimulationConfig -> registry preflight -> protocol selects active actors -> trusted
observe() filters WorldState -> policy returns Decision -> schema/protocol/mechanism
validate -> evaluate/transition -> runtime commits events -> JobResult -> report.
One action per active actor per turn. Policies see Observation, never WorldState.
WorldState.public is shared; private[actor_id] holds facts and memory. Only permitted
private/memory updates may originate from a policy. Events reconstruct committed states.
Mechanism owns legality, payoffs and state transitions; protocol owns scheduling only.
Set Mechanism.requires_joint_actions=True when every actor must act in one batch;
otherwise scheduling preflight cannot reject incompatible sequential compositions.
Validate required private initial facts, public rule fields and domain prerequisites
in validate_config/validate_state before actor calls, not only during evaluation.
Use transition helpers only if their semantics match the experiment. Do not make a
strategically poor choice illegal unless the problem's rules make it illegal.

## Capability scope at a glance
- simultaneous.v1: all actors decide in a round before joint commitment.
- sequential.v1: configured decision phases/groups; observations still use permissions.
- normal_form.v1: finite moves and supplied payoff tables.
- homogeneous_bertrand.v1: homogeneous goods, lowest-price allocation and split ties.
- differentiated_bertrand.v1: differentiated linear-demand pricing model.
- stackelberg.v1: linear inverse-demand quantity competition with leader/follower timing.
- recording.v1: collect validated actions; it supplies no economic payoff model.
- pure_nash.v1: finite action enumeration. numerical_nash.v1: bounded scalar search,
  not general constrained vector optimization. Specialized Bertrand/Stackelberg solvers
  apply only under their method requirements listed below.
- An unlisted domain has no claimed implementation. If no rule set matches, extend
  Mechanism and reuse policy/protocol/reporting rather than the runtime.

## Files and boundaries
Use experiment_extension/*.py for missing components and report generators; tests/*.py
for independently derived examples, rejection/boundary cases and parameter variation.
No scaffold edits. Scientific data belongs in native typed configuration, not JSON strings.
Use FrozenModel.from_json_values / agent_tools.fixtures at JSON/tuple boundaries.
No live actor calls in acceptance tests. The primary run is the live integration check.
Wrappers that preserve LLMPolicy's parameters and canonical observation packet may
set Actor.attributes.model_policy='llm.v1'. Central budgets, model resolution, behavior
bindings and privacy auditing then cover that wrapper. It can override response_model
with observation-dependent Pydantic validation without reading WorldState. Keep the
observation packet canonical; correction feedback belongs outside that packet.
For exhausted retries, declare Actor.attributes.safe_fallback_actions as an explicit
map of action kind to exact safe payload. A fallback needs an exhausted failed-call
trace and a nonempty explanation; it must pass mechanism legality like every action.
If a mechanism updates an actor's private state, avoid simultaneous policy private/
memory writes for that actor. Disable writable memory and supply owner-only history
as mechanism-owned private facts when appropriate; never bypass the conflict guard.
Operator actor_execution settings centrally resolve model/reasoning/token/retry settings;
author only scientific actor instructions/personas/required observation fields.
For request.actor_behaviors, copy each ActorBehaviorSpec unchanged into that actor's
llm.v1 policy_parameters.behavior. Keep shared rules in instructions; put objectives,
behavioral_instructions and background in the private typed profile. Other actors must
not see that profile. A prompted tendency is not a guaranteed action; use an explicit
deterministic policy for a guaranteed strategy. Do not mix contradictory shared objectives
with actor-specific objectives. JobManifest checks supplied profiles are preserved.
The operator owns concurrent calls, correlated transport, timing and durable resume.
Do not rebuild these in an experiment. All actors in a phase see the same precommit state.

## Notebook contract
Declare NotebookSpec(generator=..., preview_generator=..., report_version='explanatory.v1').
Preview: (JobManifest, Path) -> Path; use write_preview_notebook and ReportPreview.
It receives configuration/request only: explain the problem, assumptions, theoretical
benchmark and limitations; show calculated theory if available. No synthetic LLM results,
predicted performance, recorded decisions or performance interpretation. Leave them pending.
Final: (JobResult, Path) -> Path; use write_experiment_notebook and ReportNarrative,
ReportReference, ReportFigure/ChartSeries. Read the reports module's small public models.
Five sections: background/rationale; execution/results/benchmark interpretation;
recorded rationales once; assumptions in prose; limitations. Calculations live outside cells.
Explain specialist terms; do not repeat the table in prose. Distinguish matching actions
from matching outcomes. Reported actor rationales are not independent causal evidence.
Use assumption_prose for human explanations without raw config values or field lists.
Interpret causes/incentives and aggregate changes; do not enumerate every actor's
action/valuation/payoff a second time. Source config remains in provenance files.

## Single-pass authoring
Write a short gap analysis and a complete candidate together: draft.json, ordinary
experiment_extension/*.py, tests/*.py and summary.txt. Adapt the executable synthetic
starter; its signals, objective and scripted actors are examples, not the user's rules.
For requested LLM simulations use llm.v1 and the supplied private behavior profiles.
Do not write a prototype for a later implementation handoff. Preserve passing work.
Bundle namespace/version, source lists and test names are collected automatically.
Use component_id(experiment_id, kind, symbol_name) from agent_tools.workspace for IDs.
A component may declare test_groups=[{file, category, expected, reference}]; names are
read from that file. Expectations and independent grounding must still be authored.
No scientific rule, reference expectation or guarantee is inferred from file names.

## Validation and completion
Run `author-check` in the authoring container. It normalizes imports/formatting, checks
metadata, lint, types, tests, composition and the offline preview, then writes response.json
only when all gates pass. Its .author-check/report.json names failures and timings.
Use --only SECTION to repair named failures; unchanged passing gates are reused.
The cache is keyed by source, configuration and toolkit inputs; changed dependencies
invalidate it. No live relay is opened. Independent controller checks still run.
The following individual commands remain available for diagnosis:
Ruff: ruff check --config /opt/toolkit/pyproject.toml --no-cache experiment_extension tests
Types: mypy --config-file /opt/toolkit/pyproject.toml --cache-dir /tmp/mypy experiment_extension
Tests: PYTHONPATH=/workspace:/opt/toolkit/src python -m pytest -q -p no:cacheprovider
  -c /opt/toolkit/docker/pytest.ini /inputs/frozen_tests/tests
Assembly: python -m extension_worker.muse assemble
Finish once the stage contract validates, relevant checks pass, and the notebook content
checklist is satisfied. Additional calls must address a named unresolved issue; do not
keep rechecking unchanged passing files or polish indefinitely. There is no turn cap.
The controller separately runs offline preview, acceptance/regression and the one live run.
For small supported tasks, target a complete offline-validated candidate in about
five minutes, within a 10-15 minute total target. These are targets to measure,
not deadlines or turn caps. Complete the smallest coherent candidate and move on.
Complete code and tests in the same pass; avoid speculative extra abstractions.

The Muse session, workspace and discoveries persist across this experiment's stages.
Read current stage inputs/feedback; reuse earlier decisions and notes rather than
rediscovering them. Frozen tests/configuration and independent validation workers remain.
No past experiment artifacts are available. Agent-written tests/checks remain correlated
evidence, not independent proof.

## Exact parent methods (generated from installed interfaces)
"""


def interface_guide() -> str:
    parts = [GUIDE]
    for parent in (Mechanism, Policy, ProtocolRules, Solver, GameView):
        parts.append(f"\n### {parent.__module__}.{parent.__name__}\n")
        for name, member in inspect.getmembers(parent, inspect.isfunction):
            if name.startswith("_") and name != "__init__":
                continue
            required = "required" if getattr(member, "__isabstractmethod__", False) else "optional"
            parts.append(f"- `{name}{inspect.signature(member)}` ({required})\n")
    parts.append("\n## Approved implementations: scope comes from code/schema, not ID alone\n")
    registry = standard_registry()
    for group in ("mechanisms", "protocols", "solvers", "game_views"):
        for key, implementation in getattr(registry, group).items():
            parts.append(
                f"- {group}: `{key}` -> `{implementation.__module__}.{implementation.__name__}`; "
                f"{getattr(inspect.getmodule(implementation), '__doc__', None) or 'Inspect this implementation if selected.'}\n"
            )
            contract = getattr(implementation, "contract", None)
            if contract is not None:
                for requirement in contract.requirements:
                    parts.append(f"  - requires {requirement.id}: {requirement.description}\n")
    parts.append("\nPolicies: llm.v1 (live via host relay), scripted.v1 (deterministic tests).\n")
    parts.append("Inventory includes payload/parameter schemas, shapes and method guarantees.\n")
    return "".join(parts)


def write_starter(
    directory: Path, *, kind: str = "agent_simulation", experiment_id: str = "starter"
) -> None:
    from .starter import starter_files

    files = {"INTERFACES.md": interface_guide(), **starter_files(kind, experiment_id)}
    if any((directory / name).exists() for name in files):
        raise FileExistsError("Starter must not overwrite existing work")
    for name, content in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x") as stream:
            stream.write(content)
