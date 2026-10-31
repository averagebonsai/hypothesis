import json
from math import isclose, isfinite

import numpy as np
import pytest
from pydantic import ValidationError

from components.common.economics.segmented_logit import ConsumerSegment, SegmentedLogitDemand
from components.common.math.scalar import ScalarSearchSettings
from components.mechanisms.bertrand import PriceDomain
from components.mechanisms.differentiated_bertrand import (
    DifferentiatedBertrandGameView,
    DifferentiatedBertrandMechanism,
)
from components.solvers.numerical_nash import NumericalNashParameters, NumericalNashSolver
from examples.differentiated_bertrand import (
    DifferentiatedBertrandInputs,
    FirmInput,
    build_experiment,
    fake_response,
    illustrative_inputs,
    run_job,
)
from simulation_core.benchmark import BenchmarkRunner
from simulation_core.economics import DemandSystem
from simulation_core.execution import JobManifest, JobResult
from simulation_core.logging import replay
from simulation_core.model_gateway import FakeGateway
from simulation_core.observation import observe
from simulation_core.types import Action, ObservationPermissions, WorldState


def symmetric_inputs(lower=0.0, upper=10.0, cost=1.0, benchmark=None):
    return DifferentiatedBertrandInputs(
        firms=tuple(
            FirmInput(
                id=aid, marginal_cost=cost, price_domain=PriceDomain(lower=lower, upper=upper)
            )
            for aid in ("A", "B")
        ),
        segments=(
            ConsumerSegment(
                id="all", population=300.0, price_sensitivity=1.0, utilities={"A": 2.5, "B": 2.5}
            ),
        ),
        benchmark=benchmark or NumericalNashParameters(starts=3),
    )


def game_for(inputs):
    _, config = build_experiment(inputs)
    state = WorldState(
        tick=0,
        phase="act",
        public=config.world.initial_public_state,
        private=config.world.initial_private_state,
    )
    return (
        config,
        state,
        DifferentiatedBertrandGameView(config, state, DifferentiatedBertrandMechanism()),
    )


def profile(a, b):
    return (
        Action(actor_id="A", kind="set_price", payload={"price": float(a)}),
        Action(actor_id="B", kind="set_price", payload={"price": float(b)}),
    )


def test_symmetric_logit_exact_shares_outside_option_and_general_interface():
    demand = SegmentedLogitDemand(
        firm_ids=("A", "B"),
        segments=(
            ConsumerSegment(
                id="all", population=300.0, price_sensitivity=1.0, utilities={"A": 2.5, "B": 2.5}
            ),
        ),
    )
    assert isinstance(demand, DemandSystem)
    result = demand.evaluate({"A": 2.5, "B": 2.5})
    assert result.quantities == {"A": 100.0, "B": 100.0}
    assert result.outside_quantity == 100.0
    assert result.outside_shares["all"] == 1 / 3


def test_demand_conservation_price_effects_and_derivatives():
    inputs = illustrative_inputs()
    _, _, game = game_for(inputs)
    demand = game.parameters.demand
    base = demand.evaluate({"A": 2.0, "B": 2.5})
    increased = demand.evaluate({"A": 3.0, "B": 2.5})
    assert increased.quantities["A"] < base.quantities["A"]
    assert increased.quantities["B"] > base.quantities["B"]
    assert base.quantities["A"] > 0 and base.quantities["B"] > 0
    for a in [0.0, 1.0, 3.0, 10.0]:
        result = demand.evaluate({"A": a, "B": 2.0})
        assert sum(result.quantities.values()) <= result.total_population + 1e-9
        assert isclose(
            sum(result.quantities.values()) + result.outside_quantity,
            result.total_population,
            abs_tol=1e-9,
        )
        for sid, shares in result.segment_shares.items():
            assert isclose(sum(shares.values()) + result.outside_shares[sid], 1.0, abs_tol=1e-12)
    eps = 1e-5
    derivative = demand.own_price_derivatives({"A": 2.0, "B": 2.5})["A"]
    numeric = (
        demand.evaluate({"A": 2.0 + eps, "B": 2.5}).quantities["A"]
        - demand.evaluate({"A": 2.0 - eps, "B": 2.5}).quantities["A"]
    ) / (2 * eps)
    assert isclose(derivative, numeric, rel_tol=1e-6)


@pytest.mark.parametrize(
    "utility,alpha,price", [(10000.0, 1.0, 1.0), (-10000.0, 1.0, 10.0), (1e308, 1e308, 1e308)]
)
def test_extreme_utilities_and_prices_are_stable(utility, alpha, price):
    demand = SegmentedLogitDemand(
        firm_ids=("A", "B"),
        segments=(
            ConsumerSegment(
                id="x",
                population=100.0,
                price_sensitivity=alpha,
                utilities={"A": utility, "B": -utility},
            ),
        ),
    )
    result = demand.evaluate({"A": price, "B": price})
    assert all(isfinite(q) and q >= 0 for q in result.quantities.values())
    assert isfinite(result.outside_quantity)


def test_common_utility_translation_including_outside_does_not_change_choices():
    segment = ConsumerSegment(
        id="x", population=10.0, price_sensitivity=1.0, utilities={"A": 2.0, "B": 3.0}
    )
    base = SegmentedLogitDemand(firm_ids=("A", "B"), segments=(segment,))
    translated = SegmentedLogitDemand(
        firm_ids=("A", "B"),
        segments=(
            segment.model_copy(
                update={"utilities": {"A": 102.0, "B": 103.0}, "outside_utility": 100.0}
            ),
        ),
    )
    assert all(
        isclose(
            base.evaluate({"A": 1.0, "B": 1.5}).quantities[aid],
            translated.evaluate({"A": 1.0, "B": 1.5}).quantities[aid],
            abs_tol=1e-12,
        )
        for aid in ("A", "B")
    )


@pytest.mark.parametrize(
    "change",
    [
        "missing_utility",
        "extra_utility",
        "duplicate_firm",
        "duplicate_segment",
        "bad_population",
        "bad_alpha",
        "bad_cost",
        "bad_bounds",
        "bad_permissions",
    ],
)
def test_invalid_user_inputs_rejected(change):
    data = json.loads(illustrative_inputs().model_dump_json())
    if change == "missing_utility":
        del data["segments"][0]["utilities"]["B"]
    elif change == "extra_utility":
        data["segments"][0]["utilities"]["C"] = 1.0
    elif change == "duplicate_firm":
        data["firms"][1]["id"] = "A"
    elif change == "duplicate_segment":
        data["segments"][1]["id"] = data["segments"][0]["id"]
    elif change == "bad_population":
        data["segments"][0]["population"] = 0
    elif change == "bad_alpha":
        data["segments"][0]["price_sensitivity"] = -1
    elif change == "bad_cost":
        data["firms"][0]["marginal_cost"] = -1
    elif change == "bad_bounds":
        data["firms"][0]["price_domain"]["upper"] = -1
    else:
        data["permissions"] = {"unknown": {"public_fields": []}}
    with pytest.raises(ValidationError):
        DifferentiatedBertrandInputs.model_validate_json(json.dumps(data))


def test_user_input_transport_and_request_provenance():
    inputs = illustrative_inputs()
    assert DifferentiatedBertrandInputs.model_validate_json(inputs.model_dump_json()) == inputs
    request, config = build_experiment(inputs)
    manifest = JobManifest(request=request, simulation=config)
    assert manifest.request.supplied_inputs
    assert config.world.parameters["demand"]["segments"] == [
        s.model_dump(mode="json") for s in inputs.segments
    ]
    assert JobManifest.model_validate_json(manifest.model_dump_json()) == manifest
    with pytest.raises(ValidationError):
        DifferentiatedBertrandInputs.model_validate({"firms": inputs.firms})


def test_mechanism_gradient_matches_independent_finite_difference_and_is_pure():
    config, state, game = game_for(illustrative_inputs())
    before = (config.model_dump_json(), state.model_dump_json())
    eps = 1e-5
    gradient = game.own_payoff_gradient(profile(2.0, 2.5))["A"]
    numeric = (
        game.evaluate(profile(2.0 + eps, 2.5)).payoffs["A"]
        - game.evaluate(profile(2.0 - eps, 2.5)).payoffs["A"]
    ) / (2 * eps)
    assert isclose(gradient, numeric, rel_tol=1e-6)
    assert before == (config.model_dump_json(), state.model_dump_json())


def test_numerical_nash_matches_known_symmetric_analytic_case():
    # At p=2.5, every choice including outside has share 1/3. With c=1,
    # (p-c)*alpha*(1-share)=1, so the own-profit FOC is exactly zero.
    artifact = run_job(symmetric_inputs())
    report = artifact.benchmark
    assert report.result.status == "solved"
    eq = report.result.equilibria[0]
    assert all(abs(action.payload["price"] - 2.5) < 1e-4 for action in eq.actions)
    assert all(abs(q - 100) < 1e-3 for q in eq.outcome.metrics["quantities"].values())
    assert max(eq.regrets.values()) <= 1e-5
    assert report.result.certification == "numerical"
    assert "uniqueness" in report.result.diagnostics["scope"]
    assert any("checks" in attempt for attempt in report.result.diagnostics["attempts"])


@pytest.mark.parametrize("lower,upper,expected", [(0.0, 0.8, 0.8), (4.0, 5.0, 4.0)])
def test_constrained_equilibrium_and_bound_effects_are_reported(lower, upper, expected):
    artifact = run_job(symmetric_inputs(lower, upper))
    report = artifact.benchmark
    assert report.result.status == "solved", report.result.diagnostics
    assert all(
        abs(a.payload["price"] - expected) < 1e-5 for a in report.result.equilibria[0].actions
    )
    checks = [
        attempt["checks"]
        for attempt in report.result.diagnostics["attempts"]
        if "checks" in attempt
    ]
    assert any(
        any(c["at_lower_bound"] or c["at_upper_bound"] for c in item.values()) for item in checks
    )


def test_independent_dense_price_grid_cannot_improve_returned_equilibrium():
    inputs = symmetric_inputs()
    _config, _state, game = game_for(inputs)
    solved = NumericalNashSolver().solve(game, inputs.benchmark.model_dump(mode="json"))
    eq = solved.equilibria[0]
    for i, aid in enumerate(game.actor_ids()):
        gains = []
        for price in np.linspace(0, 10, 1001):
            candidate = list(eq.actions)
            candidate[i] = game.scalar_action(aid, float(price))
            gains.append(game.evaluate(candidate).payoffs[aid] - eq.outcome.payoffs[aid])
        assert max(gains) <= 1e-5


def test_numeric_failure_and_budget_do_not_invalidate_actor_run():
    for settings, status in [
        (NumericalNashParameters(starts=1, max_root_evaluations=1, fallback_steps=0), "failed"),
        (
            NumericalNashParameters(
                starts=1, best_response=ScalarSearchSettings(max_evaluations=3)
            ),
            "budget_exhausted",
        ),
    ]:
        artifact = run_job(symmetric_inputs(benchmark=settings))
        assert artifact.result.status == "completed"
        assert artifact.benchmark.result.status == status
        assert not artifact.benchmark.result.equilibria


def test_permissions_simultaneity_rationales_replay_and_model_call_independence():
    inputs = symmetric_inputs()
    gateway = FakeGateway(fake_response)
    artifact = run_job(inputs, gateway=gateway)
    observations = [json.loads(request.input_json)["observation"] for request in gateway.requests]
    assert len(observations) == 2
    assert observations[0]["visible"] == observations[1]["visible"]
    assert observations[0]["visible"]["history"] == []
    assert observations[0]["private"]["facts"] == {"own_marginal_cost": 1.0}
    assert all(decision.rationale for decision in artifact.result.events[-1].decisions)
    assert replay(artifact.result.events)[-1] == artifact.result.final_state
    assert JobResult.model_validate_json(artifact.model_dump_json()) == artifact
    before = artifact.result.model_dump_json()
    from components.library import standard_registry

    BenchmarkRunner(standard_registry()).run(artifact.manifest.simulation, artifact.result)
    assert artifact.result.model_dump_json() == before
    assert len(gateway.requests) == 2
    restricted = inputs.model_copy(
        update={
            "permissions": {
                aid: ObservationPermissions(
                    public_fields=("demand_model", "price_domains"),
                    private_fields=("own_marginal_cost",),
                )
                for aid in ("A", "B")
            }
        }
    )
    _request, config = build_experiment(restricted)
    state = WorldState(
        tick=0,
        phase="act",
        public=config.world.initial_public_state,
        private=config.world.initial_private_state,
    )
    obs = observe(config.world.actors[0], state, config.permissions["A"])
    assert "costs" not in obs.visible and "segments" not in obs.visible
    assert obs.private.facts == {"own_marginal_cost": 1.0}


def test_wide_price_bounds_do_not_miss_low_price_profit_peak():
    from components.common.math.scalar import maximize_scalar

    settings = ScalarSearchSettings()
    result = maximize_scalar(
        lambda p: (p - 1) / (1 + np.exp(min(p - 2.5, 700.0))), (0.0, 1e6), settings, 1e5
    )
    assert 1 < result.value < 10
    assert result.payoff > 0.5


def test_omitted_outside_utility_is_explicit_default_assumption():
    _, config = build_experiment(illustrative_inputs())
    defaults = [a for a in config.assumptions if a.path.endswith("/outside_utility")]
    assert len(defaults) == 3 and all(a.source == "default" and a.value == 0.0 for a in defaults)


def test_bounded_fallback_is_used_when_root_search_does_not_converge():
    inputs = symmetric_inputs(
        benchmark=NumericalNashParameters(starts=1, max_root_evaluations=1, fallback_steps=60)
    )
    artifact = run_job(inputs)
    assert artifact.benchmark.result.status == "solved"
    assert any(
        attempt["method"] == "damped_best_response"
        for attempt in artifact.benchmark.result.diagnostics["attempts"]
    )


def test_generic_numerical_solver_retains_multiple_solutions_and_rejects_local_minimum():
    from simulation_core.solver import BestResponseResult, DifferentiableScalarGameView
    from simulation_core.types import Outcome

    class TwoPeakGame(DifferentiableScalarGameView):
        def actor_ids(self):
            return ("A", "B")

        def action_bounds(self, actor_id):
            return (0.0, 3.0)

        def scalar_action(self, actor_id, value):
            return Action(actor_id=actor_id, kind="choose", payload={"value": float(value)})

        def action_value(self, action):
            return action.payload["value"]

        def evaluate(self, profile):
            return Outcome(
                payoffs={
                    a.actor_id: -(((a.payload["value"] - 1) * (a.payload["value"] - 2)) ** 2)
                    for a in profile
                }
            )

        def own_payoff_gradient(self, profile):
            return {
                a.actor_id: -2
                * (a.payload["value"] - 1)
                * (a.payload["value"] - 2)
                * (2 * a.payload["value"] - 3)
                for a in profile
            }

        def best_response(self, actor_id, profile):
            current = self.evaluate(profile).payoffs[actor_id]
            action = self.scalar_action(actor_id, 1.0)
            return BestResponseResult(
                actor_id=actor_id,
                current_payoff=current,
                supremum_payoff=0.0,
                gain=max(0.0, -current),
                attained=True,
                maximizing_action=action,
                witness_action=action,
                witness_payoff=0.0,
            )

    solved = NumericalNashSolver().solve(TwoPeakGame(), {"starts": 9})
    assert solved.status == "multiple" and len(solved.equilibria) >= 2
    assert all(
        min(abs(a.payload["value"] - 1), abs(a.payload["value"] - 2)) < 1e-4
        for eq in solved.equilibria
        for a in eq.actions
    )
