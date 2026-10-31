"""Textbook equal-cost duopoly theorem, certified with unilateral-payoff region checks."""

from pydantic import Field, JsonValue

from components.mechanisms.bertrand import BertrandGameView
from simulation_core.solver import Equilibrium, GameView, Solver, SolveResult
from simulation_core.types import FrozenModel


class BertrandBenchmarkParameters(FrozenModel):
    payoff_tolerance: float = Field(default=1e-9, ge=0)


class TextbookBertrandSolver(Solver):
    def solve(self, game: GameView, parameters: dict[str, JsonValue]) -> SolveResult:
        settings = BertrandBenchmarkParameters.model_validate(parameters)
        if not isinstance(game, BertrandGameView):
            return SolveResult(
                profile_domain="continuous",
                profiles_evaluated=None,
                total_profiles=None,
                status="unsupported",
                diagnostics={"reason": "Requires homogeneous Bertrand view"},
            )
        params = game.parameters
        ids = game.actor_ids()
        costs = params.marginal_costs
        if len(ids) != 2 or costs[ids[0]] != costs[ids[1]]:
            return SolveResult(
                profile_domain="continuous",
                profiles_evaluated=None,
                total_profiles=None,
                status="unsupported",
                diagnostics={
                    "reason": "The textbook certificate requires exactly two firms with identical constant costs"
                },
            )
        cost = costs[ids[0]]
        if not (
            params.price_domain.lower <= cost < params.price_domain.upper
            and cost < params.demand.choke_price
        ):
            return SolveResult(
                profile_domain="continuous",
                profiles_evaluated=None,
                total_profiles=None,
                status="unsupported",
                diagnostics={
                    "reason": "Require feasible marginal-cost price, room above it, and positive demand at cost",
                    "price_domain": params.price_domain.model_dump(mode="json"),
                },
            )
        profile = tuple(game.price_action(aid, cost) for aid in ids)
        outcome = game.evaluate(profile)
        responses = {aid: game.best_response(aid, profile) for aid in ids}
        regrets = {aid: response.gain for aid, response in responses.items()}
        if any(gain > settings.payoff_tolerance for gain in regrets.values()):
            return SolveResult(
                profile_domain="continuous",
                profiles_evaluated=None,
                total_profiles=None,
                status="failed",
                diagnostics={
                    "reason": "Unilateral-gain certificate failed",
                    "regrets": {aid: gain for aid, gain in regrets.items()},
                },
            )
        return SolveResult(
            profile_domain="continuous",
            profiles_evaluated=None,
            total_profiles=None,
            status="solved",
            equilibria=(Equilibrium(actions=profile, outcome=outcome, regrets=regrets),),
            diagnostics={
                "method": "Analytical equal-cost homogeneous Bertrand equilibrium plus region-wise best-response checks",
                "payoff_tolerance": settings.payoff_tolerance,
                "price_domain": params.price_domain.model_dump(mode="json"),
                "at_lower_bound": cost == params.price_domain.lower,
                "uniqueness_scope": "Two identical-cost firms, positive demand at cost, continuous prices, unlimited capacity",
                "scope": "Nash equilibrium, not joint-profit maximization; no price grid or tie tolerance",
                "best_responses": {
                    aid: response.model_dump(mode="json") for aid, response in responses.items()
                },
            },
        )
