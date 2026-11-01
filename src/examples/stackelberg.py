"""Two sequential LLM quantity decisions, with an independent backward-induction benchmark."""

import json
from typing import Literal, Self

from pydantic import Field, JsonValue, model_validator

from components.common.economics.models import LinearInverseDemand
from components.gateways.live import configured_gateway
from components.jobs import run_model_job
from components.mechanisms.stackelberg import QuantityDomain, StackelbergParameters
from components.protocols.sequential import DecisionPhase, SequentialParameters
from simulation_core.execution import JobResult
from simulation_core.model_gateway import FakeGateway, ModelGateway, ModelRequest
from simulation_core.request import ExperimentRequest, SuppliedInput
from simulation_core.types import (
    ActionSpace,
    Actor,
    Assumption,
    BenchmarkSpec,
    FrozenModel,
    ObservationPermissions,
    PrivateState,
    SimulationConfig,
    WorldConfig,
)


class QuantityFirmInput(FrozenModel):
    id: str = Field(min_length=1)
    marginal_cost: float = Field(ge=0)
    quantity_domain: QuantityDomain
    persona: str = ""


class StackelbergInputs(FrozenModel):
    demand: LinearInverseDemand
    leader: QuantityFirmInput
    follower: QuantityFirmInput
    max_steps: int = Field(default=2, ge=1, le=2)

    @model_validator(mode="after")
    def distinct_roles(self) -> Self:
        if self.leader.id == self.follower.id:
            raise ValueError("Leader and follower must be distinct firms")
        return self


def illustrative_inputs() -> StackelbergInputs:
    return StackelbergInputs(
        demand=LinearInverseDemand(a=100.0, b=1.0),
        leader=QuantityFirmInput(
            id="Leader", marginal_cost=20.0, quantity_domain=QuantityDomain(upper=100.0)
        ),
        follower=QuantityFirmInput(
            id="Follower", marginal_cost=20.0, quantity_domain=QuantityDomain(upper=100.0)
        ),
    )


def build_experiment(
    inputs: StackelbergInputs,
    model: str = "fake-model",
    input_source: Literal["user", "illustrative"] = "user",
) -> tuple[ExperimentRequest, SimulationConfig]:
    inputs = StackelbergInputs.model_validate(inputs.model_dump())
    leader, follower = inputs.leader.id, inputs.follower.id
    params = StackelbergParameters(
        demand=inputs.demand,
        leader_id=leader,
        follower_id=follower,
        marginal_costs={firm.id: firm.marginal_cost for firm in (inputs.leader, inputs.follower)},
        quantity_domains={
            firm.id: firm.quantity_domain for firm in (inputs.leader, inputs.follower)
        },
    )
    market: dict[str, JsonValue] = {
        "inverse_demand": {
            **inputs.demand.model_dump(mode="json"),
            "formula": "P(Q)=max(a-b*Q,0); Q=q_leader+q_follower",
        },
        "leader_id": leader,
        "follower_id": follower,
        "costs": {firm.id: firm.marginal_cost for firm in (inputs.leader, inputs.follower)},
        "quantity_domains": {
            firm.id: firm.quantity_domain.model_dump(mode="json")
            for firm in (inputs.leader, inputs.follower)
        },
        "profit_formula": "profit_i=(P(q_leader+q_follower)-c_i)*q_i",
        "timing": "Leader irrevocably commits first; follower then observes that commitment and chooses once. Market clears after both choices.",
        "assumptions": "Identical goods, constant costs, no fixed costs, all committed output is sold at the nonnegative market price. Continuous bounded quantities.",
    }
    actors = []
    for firm, role in ((inputs.leader, "leader"), (inputs.follower, "follower")):
        objective = (
            (
                "Commit your quantity to maximize your own profit, anticipating how the follower may respond after observing it. "
                "You have not observed a future follower choice."
            )
            if role == "leader"
            else (
                "Observe the leader's committed quantity in commitments and choose your own quantity to maximize your own profit. "
                "The leader cannot revise its quantity."
            )
        )
        actors.append(
            Actor(
                id=firm.id,
                kind="firm",
                action_space=ActionSpace(schemas={"set_quantity": "quantity.v1"}),
                policy_id="llm.v1",
                policy_parameters={
                    "model": model,
                    "persona": firm.persona or f"You are the {role} firm, {firm.id}.",
                    "instructions": objective
                    + " Use the market equations and feasible bounds. Explain your chosen quantity briefly, "
                    "including observed facts and any assumptions about the other firm's behavior.",
                    "required_fields": ["market"]
                    if role == "leader"
                    else ["market", "commitments"],
                    "max_attempts": 2,
                    "max_calls": 2,
                    "max_output_tokens": 4000,
                    "reasoning_effort": "minimal" if model.startswith("muse-") else None,
                },
            )
        )
    base = {
        aid: ObservationPermissions(
            public_fields=("market",), private_fields=("own_marginal_cost",)
        )
        for aid in (leader, follower)
    }
    phase_permissions = {
        "leader_commit": {leader: base[leader]},
        "follower_response": {
            follower: ObservationPermissions(
                public_fields=("market", "commitments"), private_fields=("own_marginal_cost",)
            )
        },
    }
    schedule = SequentialParameters(
        phases=(
            DecisionPhase(name="leader_commit", actor_ids=(leader,)),
            DecisionPhase(name="follower_response", actor_ids=(follower,)),
        )
    )
    config = SimulationConfig(
        world=WorldConfig(
            actors=tuple(actors),
            parameters=params.model_dump(mode="json"),
            initial_public_state={"market": market, "commitments": {}, "history": []},
            initial_private_state={
                firm.id: PrivateState(facts={"own_marginal_cost": firm.marginal_cost})
                for firm in (inputs.leader, inputs.follower)
            },
        ),
        mechanism_id="stackelberg.v1",
        protocol_id="sequential.v1",
        protocol_parameters=schedule.model_dump(mode="json"),
        permissions=base,
        phase_permissions=phase_permissions,
        max_steps=inputs.max_steps,
        benchmark=BenchmarkSpec(
            solver_id="backward_induction.v1",
            game_view_id="stackelberg.v1",
            parameters={"payoff_tolerance": 1e-9},
        ),
    )
    source: Literal["default", "user"] = "default" if input_source == "illustrative" else "user"
    assumptions = (
        Assumption(
            path="/world/parameters",
            value=config.world.parameters,
            source=source,
            rationale="Explicit linear inverse demand, nonnegative constant marginal costs and quantity bounds. Illustrative values are synthetic, not calibrated.",
        ),
        Assumption(
            path="/world/initial_public_state/market",
            value=market,
            source="textbook",
            rationale="Two-firm Stackelberg quantity leadership: first commitment is irrevocable and the follower observes it before acting. Price is truncated at zero.",
            reference="https://oyc.yale.edu/economics/econ-159/lecture-14",
        ),
        Assumption(
            path="/phase_permissions",
            value={
                phase: {
                    aid: permission.model_dump(mode="json") for aid, permission in mapping.items()
                }
                for phase, mapping in phase_permissions.items()
            },
            source="default",
            rationale="Leader sees market data; follower additionally sees the actual committed leader quantity. Neither receives the other's private state.",
        ),
        Assumption(
            path="/benchmark",
            value=config.benchmark.model_dump(mode="json") if config.benchmark else None,
            source="default",
            rationale="Backward induction assumes the follower maximizes profit at every commitment; zero-profit ties select the smallest feasible follower quantity. "
            "Leader deviation gains compare rational continuations, not the observed follower quantity held fixed. One observed follower action does not reveal its full strategy.",
        ),
    )
    config = SimulationConfig.model_validate(
        config.model_copy(update={"assumptions": assumptions}).model_dump()
    )
    supplied = (
        ()
        if input_source == "illustrative"
        else (
            SuppliedInput(
                name="inverse demand",
                value=inputs.demand.model_dump(mode="json"),
                target_path="/world/parameters/demand",
            ),
            SuppliedInput(
                name="marginal costs",
                value={firm.id: firm.marginal_cost for firm in (inputs.leader, inputs.follower)},
                target_path="/world/parameters/marginal_costs",
            ),
            SuppliedInput(
                name="quantity domains",
                value={
                    firm.id: firm.quantity_domain.model_dump(mode="json")
                    for firm in (inputs.leader, inputs.follower)
                },
                target_path="/world/parameters/quantity_domains",
            ),
        )
    )
    request = ExperimentRequest(
        hypothesis="How do LLM leader/follower quantities compare with a backward-induction equilibrium?",
        supplied_inputs=supplied,
        requirements=(
            "Follower observes the leader's actual committed quantity.",
            "Keep mathematical benchmark choices separate from actor actions.",
        ),
    )
    return request, config


def fake_response(request: ModelRequest) -> str:
    observation = json.loads(request.input_json)["observation"]
    market = observation["visible"]["market"]
    domain = market["quantity_domains"][request.actor_id]
    if request.actor_id == market["leader_id"]:
        quantity = domain["lower"] + 0.3 * (domain["upper"] - domain["lower"])
    else:
        commitment = observation["visible"]["commitments"][market["leader_id"]]
        demand = market["inverse_demand"]
        response = max(
            domain["lower"],
            min(
                domain["upper"],
                (demand["a"] - market["costs"][request.actor_id] - demand["b"] * commitment)
                / (2 * demand["b"]),
            ),
        )
        quantity = max(domain["lower"], 0.8 * response)
    return json.dumps(
        {
            "action": {
                "actor_id": request.actor_id,
                "kind": "set_quantity",
                "payload": {"quantity": quantity},
            },
            "memory_update": None,
            "private_updates": [],
            "rationale": "Deterministic off-equilibrium fixture; follower reads the actual prior commitment. Not live model behavior.",
        }
    )


def run_job(
    inputs: StackelbergInputs | None = None,
    model: str = "fake-model",
    gateway: ModelGateway | None = None,
    input_source: Literal["user", "illustrative"] | None = None,
) -> JobResult:
    request, config = build_experiment(
        inputs or illustrative_inputs(),
        model,
        input_source or ("user" if inputs is not None else "illustrative"),
    )
    return run_model_job(
        request,
        config,
        gateway if gateway is not None else FakeGateway(fake_response),
        max_calls=4,
        max_output_tokens_per_call=4200,
    )


def run_live_job(
    inputs: StackelbergInputs | None = None,
    model: str | None = None,
    input_source: Literal["user", "illustrative"] | None = None,
) -> JobResult:
    selected, gateway = configured_gateway(model)
    return run_job(inputs, selected, gateway, input_source)


if __name__ == "__main__":
    print(run_job().model_dump_json(indent=2))
