"""User-authored Pydantic inputs compile to a registered differentiated-price simulation."""

import json
from typing import Literal, Self

from pydantic import Field, JsonValue, model_validator

from components.common.economics.segmented_logit import ConsumerSegment, SegmentedLogitDemand
from components.gateways.live import configured_gateway
from components.library import standard_registry
from components.mechanisms.bertrand import PriceDomain
from components.mechanisms.differentiated_bertrand import DifferentiatedBertrandParameters
from components.solvers.numerical_nash import NumericalNashParameters
from simulation_core.execution import JobResult, JobRunner, LocalBackend
from simulation_core.model_gateway import BoundedGateway, FakeGateway, ModelGateway, ModelRequest
from simulation_core.request import ExperimentRequest, SuppliedInput
from simulation_core.types import (
    ActionSpace,
    Actor,
    Assumption,
    BenchmarkSpec,
    FrozenModel,
    ObservationPermissions,
    SimulationConfig,
    WorldConfig,
)


class FirmInput(FrozenModel):
    id: str = Field(min_length=1)
    marginal_cost: float = Field(ge=0)
    price_domain: PriceDomain
    persona: str = ""


class DifferentiatedBertrandInputs(FrozenModel):
    firms: tuple[FirmInput, ...] = Field(min_length=2)
    segments: tuple[ConsumerSegment, ...] = Field(min_length=1)
    permissions: dict[str, ObservationPermissions] | None = None
    rounds: int = Field(default=1, gt=0, le=50)
    benchmark: NumericalNashParameters = Field(default_factory=NumericalNashParameters)

    @model_validator(mode="after")
    def dimensions(self) -> Self:
        ids = tuple(firm.id for firm in self.firms)
        SegmentedLogitDemand(firm_ids=ids, segments=self.segments)
        if self.permissions is not None and set(self.permissions) != set(ids):
            raise ValueError("Explicit permissions must cover exactly the supplied firms")
        return self


def illustrative_inputs() -> DifferentiatedBertrandInputs:
    """Editable uncalibrated example data, not inferred user facts or human survey estimates."""
    return DifferentiatedBertrandInputs(
        firms=(
            FirmInput(id="A", marginal_cost=1.0, price_domain=PriceDomain(lower=0.0, upper=10.0)),
            FirmInput(id="B", marginal_cost=1.2, price_domain=PriceDomain(lower=0.0, upper=10.0)),
        ),
        segments=(
            ConsumerSegment(
                id="students",
                population=400.0,
                price_sensitivity=1.5,
                utilities={"A": 3.5, "B": 3.0},
            ),
            ConsumerSegment(
                id="professionals",
                population=350.0,
                price_sensitivity=0.8,
                utilities={"A": 4.0, "B": 4.2},
            ),
            ConsumerSegment(
                id="budget", population=250.0, price_sensitivity=2.0, utilities={"A": 2.5, "B": 2.8}
            ),
        ),
    )


def build_experiment(
    inputs: DifferentiatedBertrandInputs, model: str = "fake-model", input_source: str = "user"
) -> tuple[ExperimentRequest, SimulationConfig]:
    outside_defaults = [
        i
        for i, segment in enumerate(inputs.segments)
        if "outside_utility" not in segment.model_fields_set
    ]
    benchmark_source: Literal["default", "user"] = (
        "user" if "benchmark" in inputs.model_fields_set else "default"
    )
    rounds_source: Literal["default", "user"] = (
        "user" if "rounds" in inputs.model_fields_set else "default"
    )
    inputs = DifferentiatedBertrandInputs.model_validate(inputs.model_dump())
    params = DifferentiatedBertrandParameters(
        demand=SegmentedLogitDemand(
            firm_ids=tuple(firm.id for firm in inputs.firms), segments=inputs.segments
        ),
        marginal_costs={firm.id: firm.marginal_cost for firm in inputs.firms},
        price_domains={firm.id: firm.price_domain for firm in inputs.firms},
    )
    public: dict[str, JsonValue] = {
        "demand_model": {
            "type": "segmented_logit_with_outside_option",
            "formula": "s_ig = exp(v_ig-alpha_g*p_i)/(exp(v_0g)+sum_j exp(v_jg-alpha_g*p_j)); Q_i=sum_g N_g*s_ig",
            "meaning": "Utilities are dimensionless; price sensitivity is per price unit; outside utility is in the same scale.",
            "allocation": "Both firms may sell at different prices; consumers may choose the outside option.",
        },
        "segments": [segment.model_dump(mode="json") for segment in inputs.segments],
        "costs": {firm.id: firm.marginal_cost for firm in inputs.firms},
        "price_domains": {
            firm.id: firm.price_domain.model_dump(mode="json") for firm in inputs.firms
        },
        "history": [],
    }
    default_permissions = {
        firm.id: ObservationPermissions(
            public_fields=tuple(public) + ("market_outcome",), private_fields=("own_marginal_cost",)
        )
        for firm in inputs.firms
    }
    permissions = inputs.permissions if inputs.permissions is not None else default_permissions
    from simulation_core.types import PrivateState

    world = WorldConfig(
        actors=tuple(
            Actor(
                id=firm.id,
                kind="firm",
                action_space=ActionSpace(schemas={"set_price": "price.v1"}),
                policy_id="llm.v1",
                policy_parameters={
                    "model": model,
                    "persona": firm.persona or f"You are firm {firm.id}.",
                    "instructions": "Choose one price inside your configured bounds to maximize your own profit "
                    "in this round. Products are differentiated: lower price does not take the whole market. "
                    "Use the supplied logit demand, costs, and consumer groups. Other firms choose simultaneously. "
                    "Choose a practical approximate price, rather than performing a long exact equilibrium calculation; "
                    "a separate benchmark handles numerical equilibrium search. "
                    "Explain the observed facts and any assumptions used; never claim to know hidden rival choices.",
                    "required_fields": [],
                    "max_attempts": 2,
                    "max_calls": 2 * inputs.rounds,
                    "max_output_tokens": 4000,
                    "reasoning_effort": "minimal" if model.startswith("muse-") else None,
                },
            )
            for firm in inputs.firms
        ),
        parameters=params.model_dump(mode="json"),
        initial_public_state=public,
        initial_private_state={
            firm.id: PrivateState(facts={"own_marginal_cost": firm.marginal_cost})
            for firm in inputs.firms
        },
    )
    config = SimulationConfig(
        world=world,
        mechanism_id="differentiated_bertrand.v1",
        protocol_id="simultaneous.v1",
        protocol_parameters={"rounds": inputs.rounds},
        max_steps=inputs.rounds,
        permissions=permissions,
        benchmark=BenchmarkSpec(
            solver_id="numerical_nash.v1",
            game_view_id="differentiated_bertrand.v1",
            parameters=inputs.benchmark.model_dump(mode="json"),
        ),
    )
    source: Literal["default", "user"] = "default" if input_source == "illustrative" else "user"
    assert config.benchmark is not None
    assumptions = [
        Assumption(
            path="/world/parameters",
            value=config.world.parameters,
            source=source,
            rationale="Explicit supplied numeric inputs; illustrative inputs are synthetic, not calibrated estimates. "
            "Constant marginal costs, no fixed costs, and no capacity constraints.",
        ),
        Assumption(
            path="/world/initial_public_state/demand_model",
            value=public["demand_model"],
            source="model",
            rationale="Segmented logit is the selected structural model, with independent choices within each segment. "
            "Utility differences and price sensitivities must use coherent units; the outside option permits no purchase.",
        ),
        Assumption(
            path="/permissions",
            value={aid: p.model_dump(mode="json") for aid, p in permissions.items()},
            source="default" if inputs.permissions is None else "user",
            rationale="Complete public market information by default; explicit input permissions override it. "
            "Only own permitted private facts/memory are supplied; current rival prices are hidden.",
        ),
        Assumption(
            path="/protocol_parameters/rounds",
            value=inputs.rounds,
            source=rounds_source,
            rationale="One simultaneous stage by default; multiple stages do not establish a repeated-game equilibrium.",
        ),
        Assumption(
            path="/benchmark",
            value=config.benchmark.model_dump(mode="json"),
            source=benchmark_source,
            rationale="Compare to bounded numerical candidates, retaining all solutions found and convergence qualifications; "
            "neither global optimality nor uniqueness is proved by numerical convergence. "
            "The mathematical benchmark assumes complete information even when actor observations are restricted.",
        ),
    ]
    assumptions.extend(
        Assumption(
            path=f"/world/parameters/demand/segments/{i}/outside_utility",
            value=0.0,
            source="default",
            rationale="Outside utility is normalized to zero when omitted; product utilities must use this same scale.",
        )
        for i in outside_defaults
    )
    config = SimulationConfig.model_validate(
        config.model_copy(update={"assumptions": tuple(assumptions)}).model_dump()
    )
    supplied = (
        ()
        if input_source == "illustrative"
        else (
            SuppliedInput(
                name="consumer segments",
                value=[s.model_dump(mode="json") for s in inputs.segments],
                target_path="/world/parameters/demand/segments",
            ),
            SuppliedInput(
                name="marginal costs",
                value={firm.id: firm.marginal_cost for firm in inputs.firms},
                target_path="/world/parameters/marginal_costs",
            ),
            SuppliedInput(
                name="price bounds",
                value={firm.id: firm.price_domain.model_dump(mode="json") for firm in inputs.firms},
                target_path="/world/parameters/price_domains",
            ),
        )
    )
    request = ExperimentRequest(
        hypothesis="How do firms price under the supplied differentiated demand model, "
        "and how far are their choices from a numerical Nash benchmark?",
        supplied_inputs=supplied,
        requirements=(
            "Use the supplied firm and segment inputs without silently modifying their values.",
            "Keep LLM decisions primary and numerical benchmark actions separate.",
        ),
    )
    return request, config


def fake_response(request: ModelRequest) -> str:
    observation = json.loads(request.input_json)["observation"]
    # Fixture requires default public bounds. Restricted-information tests use custom fake callbacks.
    domain = observation["visible"]["price_domains"][request.actor_id]
    price = domain["lower"] + 0.3 * (domain["upper"] - domain["lower"])
    return json.dumps(
        {
            "action": {
                "actor_id": request.actor_id,
                "kind": "set_price",
                "payload": {"price": price},
            },
            "memory_update": None,
            "private_updates": [],
            "rationale": "Deterministic fake-gateway fixture price; not live model behavior.",
        }
    )


def run_job(
    inputs: DifferentiatedBertrandInputs,
    model: str = "fake-model",
    gateway: ModelGateway | None = None,
    input_source: str = "user",
) -> JobResult:
    request, config = build_experiment(inputs, model, input_source)
    bounded = BoundedGateway(
        gateway or FakeGateway(fake_response),
        max_calls=2 * len(inputs.firms) * inputs.rounds,
        max_output_tokens_per_call=4200,
    )
    return JobRunner(LocalBackend(standard_registry(bounded))).run(request, config)


def run_live_job(
    inputs: DifferentiatedBertrandInputs, model: str | None = None, input_source: str = "user"
) -> JobResult:
    selected, gateway = configured_gateway(model)
    return run_job(inputs, selected, gateway, input_source)


if __name__ == "__main__":
    print(run_job(illustrative_inputs(), input_source="illustrative").model_dump_json(indent=2))
