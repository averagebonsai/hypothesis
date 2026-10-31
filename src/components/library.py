"""Approved reusable components. Experiment files contain parameters, never imports."""

from components.games.normal_form import NormalFormGameView
from components.mechanisms.normal_form import MatrixParameters, MovePayload, PayoffMatrixMechanism
from components.mechanisms.recording import NumericPayload, RecordingMechanism, RecordingParameters
from components.policies.llm import LLMParameters, LLMPolicy
from components.policies.scripted import ScriptedPolicy, ScriptParameters
from components.protocols.simultaneous import RoundParameters, SimultaneousProtocol
from components.solvers.pure_nash import PureNashParameters, PureNashSolver
from simulation_core.model_gateway import ModelGateway
from simulation_core.registry import ComponentRegistry


def standard_registry(gateway: ModelGateway | None = None) -> ComponentRegistry:
    registry = ComponentRegistry(
        policies={"scripted.v1": ScriptedPolicy},
        mechanisms={"normal_form.v1": PayoffMatrixMechanism, "recording.v1": RecordingMechanism},
        protocols={"simultaneous.v1": SimultaneousProtocol},
        solvers={"pure_nash.v1": PureNashSolver},
        game_views={"normal_form.v1": NormalFormGameView},
        action_schemas={"move.v1": MovePayload, "number.v1": NumericPayload},
        parameter_schemas={
            "scripted.v1": ScriptParameters,
            "llm.v1": LLMParameters,
            "pure_nash.v1": PureNashParameters,
            "simultaneous.v1": RoundParameters,
            "normal_form.v1": MatrixParameters,
            "recording.v1": RecordingParameters,
        },
    )

    if gateway is not None:
        registry.policies["llm.v1"] = lambda parameters: LLMPolicy(parameters, gateway)
    return registry
