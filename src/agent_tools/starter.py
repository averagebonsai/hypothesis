"""Executable synthetic starters, independent of historical experiment artifacts."""

import json

from .workspace import component_id

COMPONENT = '''"""Synthetic bounded signal exercise; replace its rules for the user's problem."""
import json
from collections.abc import Sequence

from pydantic import model_validator

from simulation_core.mechanism import Mechanism
from simulation_core.types import Action, FrozenModel, Outcome, TransitionResult, WorldConfig, WorldState


class Signal(FrozenModel):
    value: float


class Parameters(FrozenModel):
    lower: float = 0.0
    upper: float = 1.0
    target: float = 0.5

    @model_validator(mode="after")
    def ordered(self) -> "Parameters":
        if self.lower > self.upper:
            raise ValueError("lower must not exceed upper")
        return self


def best_value(parameters: Parameters) -> float:
    # Independently derived point reference for this demonstration only.
    return min(parameters.upper, max(parameters.lower, parameters.target))


class SignalMechanism(Mechanism):
    def validate_config(self, config: WorldConfig) -> None:
        Parameters.model_validate(config.parameters)

    def validate_state(self, config: WorldConfig, state: WorldState) -> None:
        records = state.public.get("records", [])
        if not isinstance(records, list) or len(records) != state.tick:
            raise ValueError("One record is required per committed turn")

    def validate_actions(self, config: WorldConfig, state: WorldState, actions: Sequence[Action]) -> None:
        params = Parameters.model_validate(config.parameters)
        for action in actions:
            value = Signal.model_validate_json(json.dumps(action.payload)).value
            if action.actor_id not in {actor.id for actor in config.actors} or action.kind != "signal":
                raise ValueError("Unknown actor or action kind")
            if not params.lower <= value <= params.upper:
                raise ValueError("Signal exceeds configured bounds")

    def evaluate(self, config: WorldConfig, state: WorldState, actions: Sequence[Action]) -> Outcome:
        params = Parameters.model_validate(config.parameters)
        return Outcome(payoffs={action.actor_id: -(Signal.model_validate_json(json.dumps(action.payload)).value - params.target) ** 2 for action in actions})

    def transition(self, config: WorldConfig, state: WorldState, actions: Sequence[Action]) -> TransitionResult:
        records = state.public.get("records", [])
        if not isinstance(records, list):
            raise TypeError("Records must be a list")
        return TransitionResult(public={**state.public, "records": [*records, [action.model_dump(mode="json") for action in actions]]}, outcome=self.evaluate(config, state, actions))
'''

REPORT = '''"""Working preview/final writers; calculations stay outside notebook cells."""
from pathlib import Path

from experiment_extension.component import Parameters, best_value

from simulation_core.execution import JobManifest, JobResult
from simulation_core.reports import ReportNarrative, ReportPreview, ReportReference, assumption_prose, write_experiment_notebook, write_preview_notebook
from simulation_core.types import Action


def describe(job: JobManifest) -> ReportPreview:
    params = Parameters.model_validate(job.simulation.world.parameters)
    value = best_value(params)
    return ReportPreview(
        title="Synthetic bounded signal exercise",
        background="Participants choose a bounded numeric signal. Payoff is minus its squared distance from a target; a larger payoff means less error. This starter uses deterministic demonstration policies, not live LLM actors.",
        rationale="Demonstrate configuration, legality, state transitions, tests and recorded reporting. Replace this synthetic rule with the user's problem.",
        theory=f"The best feasible signal is the target clamped to [{params.lower:g}, {params.upper:g}]: {value:g}. Its per-turn payoff is {-(value-params.target)**2:g}. This follows directly from squared distance, not a general optimizer guarantee. No actor performance has been observed in this preview.",
        assumptions=assumption_prose(job.simulation.assumptions) or ("Synthetic demonstration rules; these are not assumptions for the user's experiment.",),
        limitations=("This synthetic example supplies no evidence about LLM behavior.",),
    )


def preview(job: JobManifest, directory: Path) -> Path:
    return write_preview_notebook(directory, describe(job))


def report(artifact: JobResult, directory: Path) -> Path:
    explanation = describe(artifact.manifest)
    params = Parameters.model_validate(artifact.manifest.simulation.world.parameters)
    value = best_value(params)
    actions = tuple(Action(actor_id=actor.id, kind="signal", payload={"value": value}) for actor in artifact.manifest.simulation.world.actors)
    reference = ReportReference(name="Squared-distance reference", explanation="Best feasible per-turn payoff for this demonstration's explicit rule, not a universal optimization claim.", actions=actions, payoffs={action.actor_id: -(value-params.target)**2 for action in actions})
    observed = sum(sum(outcome.payoffs.values()) for outcome in artifact.result.outcomes)
    narrative = ReportNarrative(title=explanation.title, background=explanation.background,
        rationale=explanation.rationale,
        interpretation=f"The recorded cumulative payoff across participants was {observed:g}. Compare the recorded choices with the feasible target reference to assess signal error. This describes the saved run; it does not establish a general behavioral pattern or participant motive.",
        assumptions=explanation.assumptions, limitations=explanation.limitations)
    return write_experiment_notebook(artifact, directory, narrative, references=(reference,))
'''

TESTS = '''"""Independent arithmetic and rejection examples; no provider is configured."""
import json
from pathlib import Path

import pytest
from experiment_extension.component import Signal, SignalMechanism
from experiment_extension.report import preview, report

from components.library import standard_registry
from simulation_core.execution import JobManifest, JobRunner, LocalBackend
from simulation_core.request import ExperimentRequest
from simulation_core.types import Action, PrivateState, SimulationConfig, WorldState


def job():
    data = json.loads(Path("draft.json").read_text())
    return JobManifest(request=ExperimentRequest(hypothesis="Synthetic signal demonstration"), simulation=SimulationConfig.from_json_values(data["simulation"]))


def test_hand_derived_payoff_and_rejection():
    config = job().simulation.world
    state = WorldState(tick=0, phase="act", public={"records": []}, private={actor.id: PrivateState() for actor in config.actors})
    mechanism = SignalMechanism()
    action = Action(actor_id=config.actors[0].id, kind="signal", payload={"value": 0.25})
    mechanism.validate_actions(config, state, (action,))
    assert mechanism.evaluate(config, state, (action,)).payoffs[action.actor_id] == -0.0625
    with pytest.raises(ValueError, match="bounds"):
        mechanism.validate_actions(config, state, (action.model_copy(update={"payload": {"value": 1.01}}),))
    transition = mechanism.transition(config, state, (action,))
    assert len(transition.public["records"]) == 1
    assert state.public == {"records": []}


def test_preview_and_recorded_report(tmp_path):
    manifest = job()
    assert SignalMechanism().validate_config(manifest.simulation.world) is None
    registry = standard_registry()
    registry.mechanisms[manifest.simulation.mechanism_id] = SignalMechanism
    registry.action_schemas[manifest.simulation.world.actors[0].action_space.schemas["signal"]] = Signal
    artifact = JobRunner(LocalBackend(registry)).run(manifest.request, manifest.simulation)
    assert all(value == -0.0625 for value in artifact.result.outcomes[0].payoffs.values())
    assert "Observed results and their interpretation are pending" in preview(manifest, tmp_path / "preview").read_text()
    assert report(artifact, tmp_path / "report").name == "results.ipynb"
'''

TOOL = '''"""Synthetic direct computation; no actors, protocol or simulation runtime."""
from simulation_core.types import FrozenModel


class Input(FrozenModel):
    value: float


def square(value: float) -> float:
    return value * value
'''


def starter_files(kind: str, experiment_id: str) -> dict[str, str]:
    if kind not in {"agent_simulation", "tool"}:
        raise ValueError("Unknown authoring route")
    components = []
    if kind == "agent_simulation":
        for category, symbol in (("mechanism", "SignalMechanism"), ("action_schema", "Signal")):
            components.append(
                {
                    "id": component_id(experiment_id, category, symbol),
                    "kind": category,
                    "purpose": "Synthetic signal demonstration; replace for the requested rules",
                    "gap_id": "rules",
                    "symbol": "experiment_extension.component:" + symbol,
                    "test_groups": [
                        {
                            "file": "tests/test_signal.py",
                            "category": "interface",
                            "expected": "Bounds, hand-derived payoff, immutable transition and offline reports hold",
                            "reference": "(0.25-0.5)^2=0.0625; 1.01 exceeds [0,1]",
                        }
                    ],
                }
            )
        mechanism = components[0]["id"]
        schema = components[1]["id"]
        config = {
            "mechanism_id": mechanism,
            "protocol_id": "simultaneous.v1",
            "protocol_parameters": {"rounds": 1},
            "world": {
                "parameters": {"lower": 0.0, "upper": 1.0, "target": 0.5},
                "initial_public_state": {"records": []},
                "actors": [
                    {
                        "id": aid,
                        "kind": "synthetic",
                        "action_space": {"schemas": {"signal": schema}},
                        "policy_id": "scripted.v1",
                        "policy_parameters": {"kind": "signal", "payload": {"value": value}},
                    }
                    for aid, value in (("left", 0.25), ("right", 0.75))
                ],
            },
            "permissions": {aid: {"public_fields": ["records"]} for aid in ("left", "right")},
        }
        extra = {"simulation": config, "tool": None}
        notebook = {
            "generator": "experiment_extension.report:report",
            "preview_generator": "experiment_extension.report:preview",
        }
        files = {
            "experiment_extension/component.py": COMPONENT,
            "experiment_extension/report.py": REPORT,
            "tests/test_signal.py": TESTS,
        }
    else:
        components = [
            {
                "kind": "utility",
                "symbol": "experiment_extension.tool:square",
                "purpose": "Synthetic direct callable",
                "gap_id": "rules",
                "input_model": "experiment_extension.tool:Input",
                "test_groups": [
                    {
                        "file": "tests/test_tool.py",
                        "category": "mathematical",
                        "expected": "Squares of -3 and 0 are 9 and 0",
                        "reference": "Hand multiplication",
                    }
                ],
            }
        ]
        extra = {
            "simulation": None,
            "tool": {"entrypoint": "experiment_extension.tool:square", "arguments": {"value": 3.0}},
        }
        notebook = None
        files = {
            "experiment_extension/tool.py": TOOL,
            "tests/test_tool.py": "from experiment_extension.tool import square\n\n\ndef test_square():\n    assert square(-3.0) == 9.0\n    assert square(0.0) == 0.0\n",
        }
    draft = {
        "summary": "Synthetic runnable starter; replace with the current request",
        "kind": kind,
        **extra,
        "bundle": {
            "gap_analysis": {
                "objective": "Synthetic workflow example, not a prior experiment",
                "decisions": [
                    {
                        "requirement": {
                            "id": "rules",
                            "description": "Synthetic numeric rule",
                            "action_shape": "scalar",
                        },
                        "disposition": "EXTEND",
                        "reason": "Demonstrate the extension interface",
                    }
                ],
            },
            "components": components,
            "notebook": notebook,
        },
    }
    return {
        **files,
        "experiment_extension/__init__.py": "",
        "draft.json": json.dumps(draft, indent=2) + "\n",
        "summary.txt": "Synthetic runnable starter; replace with the current request\n",
    }
