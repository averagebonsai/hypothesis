"""Approved reusable components. Experiment files contain parameters, never imports."""

from components.mechanisms.bertrand import (
    BertrandGameView,
    BertrandParameters,
    HomogeneousBertrandMechanism,
    PricePayload,
)
from components.mechanisms.differentiated_bertrand import (
    DifferentiatedBertrandGameView,
    DifferentiatedBertrandMechanism,
    DifferentiatedBertrandParameters,
)
from components.mechanisms.normal_form import (
    MatrixParameters,
    MovePayload,
    NormalFormGameView,
    PayoffMatrixMechanism,
)
from components.mechanisms.recording import NumericPayload, RecordingMechanism, RecordingParameters
from components.policies.llm import LLMParameters, LLMPolicy
from components.policies.scripted import ScriptedPolicy, ScriptParameters
from components.protocols.simultaneous import RoundParameters, SimultaneousProtocol
from components.solvers.bertrand import BertrandBenchmarkParameters, TextbookBertrandSolver
from components.solvers.numerical_nash import NumericalNashParameters, NumericalNashSolver
from components.solvers.pure_nash import PureNashParameters, PureNashSolver
from simulation_core.model_gateway import ModelGateway
from simulation_core.registry import ComponentRegistry


def standard_registry(gateway: ModelGateway | None = None) -> ComponentRegistry:
    registry = ComponentRegistry(
        policies={"scripted.v1": ScriptedPolicy},
        mechanisms={
            "normal_form.v1": PayoffMatrixMechanism,
            "differentiated_bertrand.v1": DifferentiatedBertrandMechanism,
            "recording.v1": RecordingMechanism,
            "homogeneous_bertrand.v1": HomogeneousBertrandMechanism,
        },
        protocols={"simultaneous.v1": SimultaneousProtocol},
        solvers={
            "pure_nash.v1": PureNashSolver,
            "numerical_nash.v1": NumericalNashSolver,
            "textbook_bertrand.v1": TextbookBertrandSolver,
        },
        game_views={
            "normal_form.v1": NormalFormGameView,
            "differentiated_bertrand.v1": DifferentiatedBertrandGameView,
            "homogeneous_bertrand.v1": BertrandGameView,
        },
        action_schemas={
            "move.v1": MovePayload,
            "number.v1": NumericPayload,
            "price.v1": PricePayload,
        },
        parameter_schemas={
            "scripted.v1": ScriptParameters,
            "differentiated_bertrand.v1": DifferentiatedBertrandParameters,
            "numerical_nash.v1": NumericalNashParameters,
            "homogeneous_bertrand.v1": BertrandParameters,
            "textbook_bertrand.v1": BertrandBenchmarkParameters,
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
