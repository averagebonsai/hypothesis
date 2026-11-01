"""General building blocks work without price, segment, or equilibrium assumptions."""

from typing import Literal

import pytest
from pydantic import ValidationError

from components.common.economics.segmented_logit import SegmentedDemandResult
from components.common.math.scalar import ScalarSearchSettings, maximize_scalar
from components.solvers.numerical_nash import NumericalNashParameters
from components.solvers.response import scalar_best_response
from simulation_core.analysis import AnalysisResult
from simulation_core.domains import ScalarInterval
from simulation_core.economics import DemandSystem, DemandSystemResult
from simulation_core.solver import DifferentiableScalarGameView
from simulation_core.types import Action, Outcome


class QuadraticGame(DifferentiableScalarGameView):
    def actor_ids(self):
        return ("worker",)

    def action_bounds(self, actor_id):
        return (-3.0, 3.0)

    def scalar_action(self, actor_id, value):
        return Action(actor_id=actor_id, kind="choose_effort", payload={"effort": value})

    def action_value(self, action):
        return action.payload["effort"]

    def evaluate(self, profile):
        value = self.action_value(profile[0])
        return Outcome(payoffs={"worker": -((value - 1.25) ** 2)})

    def own_payoff_gradient(self, profile):
        return {"worker": -2 * (self.action_value(profile[0]) - 1.25)}

    def best_response(self, actor_id, profile):
        return scalar_best_response(self, actor_id, profile, ScalarSearchSettings())


def test_nonsegmented_joint_demand_uses_the_general_contract():
    class SimpleDemand(DemandSystem):
        def evaluate(self, prices):
            return DemandSystemResult(
                quantities={aid: max(10 - value, 0) for aid, value in prices.items()}
            )

    assert SimpleDemand().evaluate({"x": 3.0}).quantities == {"x": 7.0}
    with pytest.raises(ValidationError):
        DemandSystemResult(quantities={"x": -1.0})
    with pytest.raises(ValidationError):
        DemandSystemResult(quantities={"x": float("inf")})


def test_specialized_demand_still_enforces_conservation():
    with pytest.raises(ValidationError, match="conserve population"):
        SegmentedDemandResult(
            quantities={"x": 2.0},
            segment_shares={"s": {"x": 0.5}},
            outside_shares={"s": 0.5},
            outside_quantity=1.0,
            total_population=10.0,
        )


def test_interval_supports_negative_mathematical_coordinates():
    interval = ScalarInterval(lower=-3.0, upper=2.0)
    assert interval.contains(-2.0) and not interval.contains(3.0)
    with pytest.raises(ValidationError):
        ScalarInterval(lower=2.0, upper=2.0)


def test_general_analysis_result_can_represent_a_nonequilibrium_analysis():
    class AllocationResult(AnalysisResult):
        status: Literal["feasible"]
        allocation: tuple[float, ...]
        objective_value: float

    result = AllocationResult(status="feasible", allocation=(1.0, 2.0), objective_value=3.0)
    assert "equilibria" not in result.model_dump()
    assert AllocationResult.model_validate_json(result.model_dump_json()) == result


def test_scalar_search_and_old_tolerance_inputs_have_neutral_output_names():
    settings = ScalarSearchSettings(price_tolerance=1e-7)
    assert settings.action_tolerance == 1e-7
    assert "price_tolerance" not in settings.model_dump()
    assert NumericalNashParameters(price_tolerance=1e-6).action_tolerance == 1e-6
    result = maximize_scalar(lambda x: -((x - 1.25) ** 2), (-3.0, 3.0), settings, 0.0)
    assert result.value == pytest.approx(1.25, abs=1e-5)
    assert result.objective_value == pytest.approx(0.0, abs=1e-9)


def test_numerical_candidate_does_not_claim_a_certified_supremum():
    game = QuadraticGame()
    response = game.best_response("worker", (game.scalar_action("worker", 0.0),))
    assert response.estimated_best_payoff == pytest.approx(0.0, abs=1e-9)
    assert response.supremum_payoff is None and response.attained is None
    assert response.maximizing_action is None
    assert response.witness_action.payload["effort"] == pytest.approx(1.25, abs=1e-5)


def test_numerical_solver_uses_same_search_settings_for_verification_and_diagnostics():
    from components.solvers.numerical_nash import NumericalNashSolver

    game = QuadraticGame()
    parameters = {"starts": 1, "best_response": {"grid_points": 17, "action_tolerance": 1e-7}}
    solver = NumericalNashSolver()
    solved = solver.solve(game, parameters)
    assert solved.status == "solved"
    verification = next(
        attempt["checks"]["worker"]
        for attempt in solved.diagnostics["attempts"]
        if "checks" in attempt
    )
    responses = solver.best_responses(game, (game.scalar_action("worker", 0.0),), parameters)
    assert verification["settings"] == responses["worker"].diagnostics["settings"]
    assert verification["settings"]["grid_points"] == 17
    assert responses["worker"].diagnostics["independent"] is not None


def test_numerical_capability_check_rejects_invalid_scalar_domains_without_search():
    from components.solvers.numerical_nash import NumericalNashSolver

    class InvalidDomain(QuadraticGame):
        def action_bounds(self, actor_id):
            return (3.0, 3.0)

        def evaluate(self, profile):
            raise AssertionError("Compatibility validation must not execute a payoff search")

    with pytest.raises(ValueError, match="lower < upper"):
        NumericalNashSolver().validate_game(InvalidDomain())
