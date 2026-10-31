import json
import random
from itertools import pairwise
from math import isclose, nextafter

import pytest
from pydantic import ValidationError

from components.common.economics.models import (
    ConstantMarginalCost,
    LinearDemand,
    LowestPriceAllocation,
    RevenueMinusCost,
)
from components.library import standard_registry
from components.mechanisms.bertrand import BertrandGameView, HomogeneousBertrandMechanism
from components.solvers.pure_nash import PureNashSolver
from examples.bertrand import BertrandExampleSettings, build_experiment, fake_response, run_job
from simulation_core.benchmark import BenchmarkRunner
from simulation_core.economics import AllocationRule, CostModel, DemandModel, ProfitModel
from simulation_core.logging import replay
from simulation_core.model_gateway import BoundedGateway, FakeGateway
from simulation_core.observation import observe
from simulation_core.runtime import SimulationRuntime
from simulation_core.solver import BestResponseGameView, FiniteGameView
from simulation_core.types import (
    Action,
    ActionSpace,
    Actor,
    ObservationPermissions,
    PrivateState,
    WorldState,
)


def state_for(config):
    return WorldState(
        tick=0,
        phase="act",
        public=config.world.initial_public_state,
        private={actor.id: PrivateState() for actor in config.world.actors},
    )


def profile(*prices, ids=("A", "B")):
    return tuple(
        Action(actor_id=aid, kind="set_price", payload={"price": float(price)})
        for aid, price in zip(ids, prices)
    )


def market(prices, settings=None):
    config = build_experiment(settings=settings)
    mechanism = HomogeneousBertrandMechanism()
    return mechanism.evaluate(config.world, state_for(config), profile(*prices))


def test_economic_components_implement_general_parents():
    assert isinstance(LinearDemand(a=100.0, b=1.0), DemandModel)
    assert isinstance(ConstantMarginalCost(marginal_cost=20.0), CostModel)
    assert isinstance(LowestPriceAllocation(), AllocationRule)
    assert isinstance(RevenueMinusCost(), ProfitModel)
    for parent in (DemandModel, CostModel, AllocationRule, ProfitModel):
        with pytest.raises(TypeError):
            parent()


@pytest.mark.parametrize(
    "prices,quantities,profits",
    [
        ((30, 25), {"A": 0.0, "B": 75.0}, {"A": 0.0, "B": 375.0}),
        ((25, 30), {"A": 75.0, "B": 0.0}, {"A": 375.0, "B": 0.0}),
        ((30, 30), {"A": 35.0, "B": 35.0}, {"A": 350.0, "B": 350.0}),
        ((20, 20), {"A": 40.0, "B": 40.0}, {"A": 0.0, "B": 0.0}),
        ((10, 10), {"A": 45.0, "B": 45.0}, {"A": -450.0, "B": -450.0}),
        ((100, 100), {"A": 0.0, "B": 0.0}, {"A": 0.0, "B": 0.0}),
    ],
)
def test_piecewise_allocation_and_profit_benchmarks(prices, quantities, profits):
    outcome = market(prices)
    assert outcome.metrics["quantities"] == quantities
    assert outcome.payoffs == profits
    assert sum(quantities.values()) == outcome.metrics["total_quantity"]


def test_no_fuzzy_ties_and_nonnegative_truncated_demand():
    prices = (nextafter(30.0, 0.0), 30.0)
    assert market(prices).metrics["quantities"]["B"] == 0.0
    demand = LinearDemand(a=100.0, b=1.0)
    assert demand.quantity(101.0) == 0.0
    assert (
        market((120, 130), BertrandExampleSettings(price_upper=150.0)).metrics["total_quantity"]
        == 0.0
    )


def test_own_price_demand_weakly_decreases_including_tie_jump():
    prices = [0.0, 10.0, 20.0, nextafter(30.0, 0.0), 30.0, nextafter(30.0, 100.0), 60.0, 100.0]
    quantities = [market((p, 30.0)).metrics["quantities"]["A"] for p in prices]
    assert all(a >= b for a, b in pairwise(quantities))


def test_pure_evaluation_and_independent_runs():
    config = build_experiment()
    state = state_for(config)
    before = (config.model_dump_json(), state.model_dump_json())
    mechanism = HomogeneousBertrandMechanism()
    for prices in [(20, 20), (20, 30), (30, 30), (25, 30)]:
        mechanism.evaluate(config.world, state, profile(*prices))
    assert before == (config.model_dump_json(), state.model_dump_json())
    first = run_job()
    assert first == run_job()
    assert replay(first.result.events)[-1] == first.result.final_state
    first.result.final_state.public["history"].clear()
    assert len(run_job().result.final_state.public["history"]) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"price": -1.0},
        {"price": 101.0},
        {"price": float("nan")},
        {"price": float("inf")},
        {"price": "20"},
        {"price": True},
        {"price": 20.0, "extra": True},
    ],
)
def test_invalid_prices_never_reach_transition(payload):
    config = build_experiment()

    def invalid_response(request):
        data = json.loads(fake_response(request))
        data["action"]["payload"] = payload
        return json.dumps(data)

    registry = standard_registry(BoundedGateway(FakeGateway(invalid_response)))

    class NoTransition(HomogeneousBertrandMechanism):
        def transition(self, *args):
            pytest.fail("Invalid price reached transition")

    registry.mechanisms["homogeneous_bertrand.v1"] = NoTransition
    with pytest.raises((ValueError, RuntimeError)):
        SimulationRuntime(registry).run(config)


@pytest.mark.parametrize(
    "field,value",
    [
        ("a", 0.0),
        ("b", 0.0),
        ("b", -1.0),
        ("marginal_cost", -1.0),
        ("price_upper", 20.0),
        ("price_lower", 21.0),
        ("marginal_cost", 100.0),
    ],
)
def test_invalid_economic_assumptions_rejected(field, value):
    with pytest.raises(ValidationError):
        BertrandExampleSettings(**{field: value})


def test_textbook_equilibrium_is_certified_by_unilateral_checks():
    artifact = run_job()
    report = artifact.benchmark
    assert report.result.status == "solved"
    assert report.result.profile_domain == "continuous"
    assert report.result.total_profiles is None
    eq = report.result.equilibria[0]
    assert {a.actor_id: a.payload["price"] for a in eq.actions} == {"A": 20.0, "B": 20.0}
    assert eq.outcome.payoffs == {"A": 0.0, "B": 0.0}
    assert eq.outcome.metrics["quantities"] == {"A": 40.0, "B": 40.0}
    assert eq.regrets == {"A": 0.0, "B": 0.0}
    assert report.comparisons[0].numeric_action_deltas == {
        "A": {"price": 10.0},
        "B": {"price": 5.0},
    }
    assert report.comparisons[0].payoff_deltas == {"A": 0.0, "B": 375.0}
    assert report.observed_regrets == {"A": 375.0, "B": 325.0}


def test_strict_undercutting_supremum_is_not_misreported_as_attained():
    config = build_experiment()
    game = BertrandGameView(config, state_for(config), HomogeneousBertrandMechanism())
    response = game.best_response("A", profile(30, 25))
    assert not response.attained
    assert response.maximizing_action is None
    assert response.supremum_payoff == 375.0
    assert response.witness_action.payload["price"] < 25.0
    assert isclose(response.witness_payoff, 375.0, abs_tol=1e-10)
    # Rival prices above the monopoly price: the best response is attained at 60.
    response = game.best_response("A", profile(30, 80))
    assert response.attained and response.maximizing_action.payload["price"] == 60.0
    assert response.supremum_payoff == 1600.0
    assert isinstance(game, BestResponseGameView) and not isinstance(game, FiniteGameView)
    assert PureNashSolver().solve(game, {}).status == "unsupported"


def reference_profit(own, rival, c=20.0):
    demand = max(100.0 - own, 0.0)
    quantity = demand if own < rival else demand / 2 if own == rival else 0.0
    return (own - c) * quantity


def test_best_response_region_analysis_dominates_independent_dense_grid():
    config = build_experiment()
    game = BertrandGameView(config, state_for(config), HomogeneousBertrandMechanism())
    rng = random.Random(42)
    for rival in [0.0, 10.0, 20.0, 25.0, 60.0, 80.0, 100.0] + [
        rng.uniform(0, 100) for _ in range(15)
    ]:
        own = rng.uniform(0, 100)
        response = game.best_response("A", profile(own, rival))
        dense = [reference_profit(i / 10, rival) for i in range(1001)]
        dense.extend(reference_profit(p, rival) for p in (rival, nextafter(rival, 0.0), 60.0))
        assert response.supremum_payoff + 1e-9 >= max(dense)
        assert response.witness_payoff <= response.supremum_payoff + 1e-9
        if response.attained:
            assert isclose(response.supremum_payoff, response.witness_payoff, abs_tol=1e-9)
    assert max(reference_profit(i / 10, rival=20.0) for i in range(1001)) == 0.0


def test_unsupported_benchmark_does_not_contaminate_actor_run():
    config = build_experiment()
    params = dict(config.world.parameters)
    params["marginal_costs"] = {"A": 20.0, "B": 25.0}
    config = config.model_copy(
        update={"assumptions": (), "world": config.world.model_copy(update={"parameters": params})}
    )
    registry = standard_registry(BoundedGateway(FakeGateway(fake_response)))
    run = SimulationRuntime(registry).run(config)
    before = (config.model_dump_json(), run.model_dump_json())
    report = BenchmarkRunner(registry).run(config, run)
    assert report.result.status == "unsupported"
    assert report.comparisons == ()
    assert before == (config.model_dump_json(), run.model_dump_json())
    assert run.status == "completed"


def test_arbitrary_actor_ids_multifirm_allocation_and_private_information():
    spec = BertrandExampleSettings(actor_ids=("north_shop", "south_shop"))
    artifact = run_job(spec)
    assert set(artifact.result.outcomes[0].payoffs) == set(spec.actor_ids)
    config = build_experiment()
    third = Actor(
        id="C",
        kind="firm",
        policy_id="scripted.v1",
        policy_parameters={"kind": "set_price", "payload": {"price": 20.0}},
        action_space=ActionSpace(schemas={"set_price": "price.v1"}),
    )
    params = dict(config.world.parameters)
    params["marginal_costs"] = {"A": 20.0, "B": 20.0, "C": 20.0}
    world = config.world.model_copy(
        update={"actors": (*config.world.actors, third), "parameters": params}
    )
    mechanism = HomogeneousBertrandMechanism()
    mechanism.validate_config(world)
    outcome = mechanism.evaluate(world, state_for(config), profile(20, 20, 40, ids=("A", "B", "C")))
    assert outcome.metrics["quantities"] == {"A": 40.0, "B": 40.0, "C": 0.0}
    state = state_for(config).model_copy(
        update={
            "private": {
                "A": PrivateState(facts={"secret": "A"}),
                "B": PrivateState(facts={"secret": "B"}),
            }
        }
    )
    obs = observe(
        config.world.actors[0],
        state,
        ObservationPermissions(public_fields=("market",), private_fields=("secret",)),
    )
    assert obs.private.facts == {"secret": "A"}
    assert "market_outcome" not in obs.visible and "history" not in obs.visible


def test_simultaneous_observations_rationales_and_benchmark_independence():
    gateway = FakeGateway(fake_response)
    artifact = run_job(gateway=gateway)
    observations = [json.loads(req.input_json)["observation"] for req in gateway.requests]
    assert len(observations) == 2
    assert observations[0]["visible"] == observations[1]["visible"]
    assert observations[0]["visible"]["history"] == []
    assert "q_i = Q(p_i)/2" in observations[0]["visible"]["market"]["firm_demand_piecewise"]
    assert len(gateway.requests) == 2  # benchmark makes no model calls
    assert all(decision.rationale for decision in artifact.result.events[-1].decisions)
    assert artifact.result.final_state.public["history"] == [{"A": 30.0, "B": 25.0}]


@pytest.mark.parametrize(
    "a,b,c,upper",
    [
        (100.0, 2.0, 10.0, 100.0),
        (200.0, 1.0, 30.0, 100.0),
        (50.0, 0.5, 7.25, 120.0),
        (100.0, 1.0, 0.0, 100.0),
        (10.0, 2.0, 1.0, 100.0),
    ],
)
def test_analytical_benchmark_uses_configured_parameters(a, b, c, upper):
    artifact = run_job(BertrandExampleSettings(a=a, b=b, marginal_cost=c, price_upper=upper))
    equilibrium = artifact.benchmark.result.equilibria[0]
    assert artifact.benchmark.result.status == "solved"
    assert all(action.payload["price"] == c for action in equilibrium.actions)
    assert all(
        isclose(q, (a - b * c) / 2, abs_tol=1e-10)
        for q in equilibrium.outcome.metrics["quantities"].values()
    )
    assert all(
        isclose(profit, 0.0, abs_tol=1e-10) for profit in equilibrium.outcome.payoffs.values()
    )
    assert max(equilibrium.regrets.values()) == 0.0
