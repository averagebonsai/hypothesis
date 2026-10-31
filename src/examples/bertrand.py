"""Typed textbook homogeneous Bertrand experiment; shared runtime and generic LLMPolicy."""

import json
from typing import Self

from pydantic import Field, JsonValue, model_validator

from components.common.economics.models import LinearDemand
from components.gateways.live import configured_gateway
from components.library import standard_registry
from components.mechanisms.bertrand import BertrandParameters, PriceDomain
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


class BertrandExampleSettings(FrozenModel):
    a: float = Field(default=100.0, gt=0)
    b: float = Field(default=1.0, gt=0)
    marginal_cost: float = Field(default=20.0, ge=0)
    price_lower: float = Field(default=0.0, ge=0)
    price_upper: float = Field(default=100.0, gt=0)
    actor_ids: tuple[str, str] = ("A", "B")
    rounds: int = Field(default=1, gt=0, le=50)

    @model_validator(mode="after")
    def textbook_scope(self) -> Self:
        demand = LinearDemand(a=self.a, b=self.b)
        PriceDomain(lower=self.price_lower, upper=self.price_upper)
        if len(set(self.actor_ids)) != 2 or any(not aid for aid in self.actor_ids):
            raise ValueError("Example requires two distinct nonempty actor IDs")
        if (
            not self.price_lower <= self.marginal_cost < self.price_upper
            or self.marginal_cost >= demand.choke_price
        ):
            raise ValueError("Textbook example requires feasible marginal cost below choke price")
        return self


def build_experiment(
    model: str = "fake-model", settings: BertrandExampleSettings | None = None
) -> SimulationConfig:
    spec = settings or BertrandExampleSettings()
    params = BertrandParameters(
        demand=LinearDemand(a=spec.a, b=spec.b),
        marginal_costs={aid: spec.marginal_cost for aid in spec.actor_ids},
        price_domain=PriceDomain(lower=spec.price_lower, upper=spec.price_upper),
    )
    market: dict[str, JsonValue] = {
        "demand": {"a": spec.a, "b": spec.b, "formula": "Q(P) = max(a - b*P, 0)"},
        "firm_demand_piecewise": "For two firms i and j: q_i = Q(p_i) if p_i < p_j; "
        "q_i = Q(p_i)/2 if p_i = p_j; q_i = 0 if p_i > p_j.",
        "costs": {aid: cost for aid, cost in params.marginal_costs.items()},
        "cost_formula": "C_i(q_i) = c_i*q_i; no fixed costs",
        "profit_formula": "profit_i = (p_i - c_i)*q_i",
        "price_domain": params.price_domain.model_dump(mode="json"),
        "price_convention": "Continuous prices, no price grid or rounding; ties require exact equality.",
        "capacity": "Unlimited; firms supply allocated demand.",
        "timing": "One-shot simultaneous choices; rival's uncommitted price is not visible.",
    }
    actors = tuple(
        Actor(
            id=aid,
            kind="firm",
            action_space=ActionSpace(schemas={"set_price": "price.v1"}),
            policy_id="llm.v1",
            policy_parameters={
                "model": model,
                "instructions": "Choose one feasible price to maximize your own profit "
                "in this round. Read the public piecewise demand function and costs. "
                "Rivals choose simultaneously. Explain your price using these facts; do not assume "
                "you have observed the rival's current choice.",
                "persona": f"You are firm {aid}, selling an identical product.",
                "required_fields": ["market"],
                "max_attempts": 2,
                "max_calls": 2 * spec.rounds,
                "max_output_tokens": 1000,
                "reasoning_effort": "low" if model.startswith("muse-") else None,
            },
        )
        for aid in spec.actor_ids
    )
    permissions = {
        aid: ObservationPermissions(public_fields=("market", "history", "market_outcome"))
        for aid in spec.actor_ids
    }
    config = SimulationConfig(
        world=WorldConfig(
            actors=actors,
            parameters=params.model_dump(mode="json"),
            initial_public_state={"market": market, "history": []},
        ),
        mechanism_id="homogeneous_bertrand.v1",
        protocol_id="simultaneous.v1",
        protocol_parameters={"rounds": spec.rounds},
        permissions=permissions,
        benchmark=BenchmarkSpec(
            solver_id="textbook_bertrand.v1",
            game_view_id="homogeneous_bertrand.v1",
            parameters={"payoff_tolerance": 1e-9},
        ),
        max_steps=spec.rounds,
    )
    assumptions = (
        Assumption(
            path="/world/parameters",
            value=config.world.parameters,
            source="default",
            rationale="Illustrative linear demand and identical constant marginal costs; numbers are "
            "explicit synthetic configuration, not calibrated data. Prices are continuous and bounded.",
        ),
        Assumption(
            path="/world/initial_public_state/market",
            value=market,
            source="textbook",
            rationale="Homogeneous products, unlimited capacity, no fixed costs, complete information; "
            "lowest price takes all demand and an exact tie splits it equally. Demand is truncated at zero.",
            reference="https://www.princeton.edu/~dixitak/Teaching/MicroLowCalculus/Slides/Lec16.pdf",
        ),
        Assumption(
            path="/permissions",
            value={aid: p.model_dump(mode="json") for aid, p in permissions.items()},
            source="default",
            rationale="Each firm knows demand, both marginal costs and price bounds; "
            "only committed past prices and outcomes are public. Private memory remains actor-specific.",
        ),
        Assumption(
            path="/protocol_parameters/rounds",
            value=spec.rounds,
            source="default",
            rationale="One simultaneous round by default. More rounds are independent spot-market "
            "comparisons to a stage-game benchmark, not a repeated-game equilibrium claim.",
        ),
    )
    return SimulationConfig.model_validate(
        config.model_copy(update={"assumptions": assumptions}).model_dump()
    )


def fake_response(request: ModelRequest) -> str:
    """Off-equilibrium fixture, determined by actor order in the permitted market data."""
    market = json.loads(request.input_json)["observation"]["visible"]["market"]
    ids = list(market["costs"])
    cost = market["costs"][request.actor_id]
    fraction = 0.125 if request.actor_id == ids[0] else 0.0625
    price = cost + fraction * (market["price_domain"]["upper"] - cost)
    return json.dumps(
        {
            "action": {
                "actor_id": request.actor_id,
                "kind": "set_price",
                "payload": {"price": price},
            },
            "memory_update": None,
            "private_updates": [],
            "rationale": "Deterministic off-equilibrium fake-gateway price for testing; not live LLM behavior.",
        }
    )


def run_job(
    settings: BertrandExampleSettings | None = None,
    model: str = "fake-model",
    gateway: ModelGateway | None = None,
) -> JobResult:
    config = build_experiment(model, settings)
    bounded = BoundedGateway(
        gateway or FakeGateway(fake_response),
        max_calls=4 * config.max_steps,
        max_output_tokens_per_call=1200,
    )
    request = ExperimentRequest(
        hypothesis="How do LLM firms price under textbook homogeneous Bertrand competition, "
        "and how far are their actions and outcomes from the Bertrand-Nash equilibrium?",
        requirements=(
            "Lowest-price seller takes the market; exactly tied firms split demand equally.",
            "Market demand is linear and firms set prices simultaneously.",
        ),
        supplied_inputs=(
            SuppliedInput(
                name="demand functional form",
                value="Q(P) = max(a - b*P, 0)",
                target_path="/world/initial_public_state/market/demand/formula",
            ),
        ),
    )
    return JobRunner(LocalBackend(standard_registry(bounded))).run(request, config)


def run_live_job(
    settings: BertrandExampleSettings | None = None, model: str | None = None
) -> JobResult:
    selected, gateway = configured_gateway(model)
    return run_job(settings, selected, gateway)


if __name__ == "__main__":
    print(run_job().model_dump_json(indent=2))
