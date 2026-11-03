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

## Validation and completion
Ruff: ruff check --config /opt/toolkit/pyproject.toml --no-cache experiment_extension tests
Types: mypy --config-file /opt/toolkit/pyproject.toml --cache-dir /tmp/mypy experiment_extension
Tests: PYTHONPATH=/workspace:/opt/toolkit/src python -m pytest -q -p no:cacheprovider
  -c /opt/toolkit/docker/pytest.ini /inputs/frozen_tests/tests
Assembly: python -m extension_worker.muse assemble
Finish once the stage contract validates, relevant checks pass, and the notebook content
checklist is satisfied. Additional calls must address a named unresolved issue; do not
keep rechecking unchanged passing files or polish indefinitely. There is no turn cap.
The controller separately runs offline preview, acceptance/regression and the one live run.
For small simulations aim for roughly two minutes planning and three minutes implementation,
within a 10-15 minute total target. These are soft targets, not deadlines or turn caps.
Write the minimal coherent plan and independently grounded tests, assemble and move on.
Avoid implementing a full prototype during planning unless needed to resolve a named gap.
Keep any necessary prototype for implementation; avoid speculative extra abstractions.

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


MECHANISM = '''"""Template only: implement missing rules, or delete if reusing a mechanism."""
from collections.abc import Sequence

from simulation_core.mechanism import Mechanism
from simulation_core.types import Action, Outcome, TransitionResult, WorldConfig, WorldState


class CustomMechanism(Mechanism):
    def validate_config(self, config: WorldConfig) -> None:
        raise NotImplementedError("Validate typed parameters and supported actors")

    def validate_state(self, config: WorldConfig, state: WorldState) -> None:
        raise NotImplementedError("Check state invariants")

    def validate_actions(self, config: WorldConfig, state: WorldState, actions: Sequence[Action]) -> None:
        raise NotImplementedError("Check complete active profile and domain legality")

    def evaluate(self, config: WorldConfig, state: WorldState, actions: Sequence[Action]) -> Outcome:
        raise NotImplementedError("Calculate payoffs/metrics without mutating input")

    def transition(self, config: WorldConfig, state: WorldState, actions: Sequence[Action]) -> TransitionResult:
        raise NotImplementedError("Return next state/outcome; runtime commits events")
'''

REPORT = '''"""Preview uses only configuration; final report uses actual recorded results."""
from pathlib import Path

from simulation_core.execution import JobManifest, JobResult


def preview(job: JobManifest, directory: Path) -> Path:
    # Calculate/explain theory from job.simulation, without running any actor.
    # Use ReportPreview + write_preview_notebook from simulation_core.reports.
    raise NotImplementedError("Problem, theory, assumptions, limitations; results pending")


def report(artifact: JobResult, directory: Path) -> Path:
    # Use ReportNarrative + write_experiment_notebook from simulation_core.reports.
    # Derive observed interpretation from artifact, never assumed actor behavior.
    raise NotImplementedError("Five-section explanatory report from recorded result")
'''


def write_starter(directory: Path, *, kind: str = "agent_simulation") -> None:
    if kind not in {"agent_simulation", "tool"}:
        raise ValueError("Unknown authoring route")
    directory.mkdir(parents=True, exist_ok=True)
    files = {"INTERFACES.md": interface_guide(), "experiment_extension/__init__.py": ""}
    if kind == "agent_simulation":
        files.update(
            {
                "experiment_extension/component.py": MECHANISM,
                "experiment_extension/report.py": REPORT,
            }
        )
    else:
        files["experiment_extension/tool.py"] = (
            '"""Define a typed problem-specific callable; no simulation scaffold needed."""\n'
        )
    for name, content in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x") as stream:
            stream.write(content)
