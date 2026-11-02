"""Textbook equal-cost duopoly theorem, certified with unilateral-payoff region checks."""

from pydantic import Field, JsonValue

from components.common.economics.models import LinearDemand, LowestPriceAllocation, RevenueMinusCost
from components.mechanisms.bertrand import BertrandGameView, HomogeneousBertrandMechanism
from components.solvers.requirements import PURE_PAYOFFS, VIEW, model_evidence
from simulation_core.contracts import (
    MethodContract,
    MethodRequirement,
    RequirementEvidence,
    checked,
)
from simulation_core.solver import Equilibrium, GameView, Solver, SolveResult
from simulation_core.types import FrozenModel


class BertrandBenchmarkParameters(FrozenModel):
    payoff_tolerance: float = Field(default=1e-9, ge=0)


class TextbookBertrandSolver(Solver):
    required_game_type = BertrandGameView
    profile_domain = "continuous"
    contract = MethodContract(
        name="Textbook homogeneous Bertrand duopoly theorem",
        requirements=(
            VIEW,
            PURE_PAYOFFS,
            MethodRequirement(
                id="homogeneous_rules",
                description="Homogeneous product, linear truncated demand, unlimited supply, exact lowest-price allocation and equal tie splitting",
            ),
            MethodRequirement(
                id="equal_cost_duopoly",
                description="Exactly two firms with equal nonnegative constant marginal costs",
            ),
            MethodRequirement(
                id="interior_cost_price",
                description="Marginal-cost price is feasible, room remains above it, and demand at cost is positive",
            ),
        ),
        guarantees=(
            "Marginal-cost price profile is a Nash equilibrium after analytical unilateral checks pass",
        ),
        limitations=(
            "Complete-information rational benchmark; no prediction of LLM behavior",
            "Requires this theorem's market rules, not convexity of discontinuous Bertrand profits",
            "Floating-point arithmetic and payoff tolerance apply",
        ),
    )

    def requirement_evidence(
        self, game: GameView, parameters: dict[str, JsonValue]
    ) -> tuple[RequirementEvidence, ...]:
        evidence = super().requirement_evidence(game, parameters)
        BertrandBenchmarkParameters.from_json_values(parameters)
        if not isinstance(game, BertrandGameView):
            return evidence
        p, ids = game.parameters, game.actor_ids()
        equal = len(ids) == 2 and p.marginal_costs[ids[0]] == p.marginal_costs[ids[1]]
        cost = p.marginal_costs[ids[0]] if ids else float("inf")
        return (
            *evidence,
            model_evidence(
                "homogeneous_rules",
                type(game) is BertrandGameView
                and type(game.mechanism) is HomogeneousBertrandMechanism
                and type(game.mechanism.allocation) is LowestPriceAllocation
                and type(game.mechanism.profit_model) is RevenueMinusCost
                and type(p.demand) is LinearDemand,
                "Encoded by the validated homogeneous Bertrand mechanism and its allocation/demand implementation",
            ),
            checked(
                "equal_cost_duopoly", equal, "Actor count and configured marginal costs checked"
            ),
            checked(
                "interior_cost_price",
                p.price_domain.lower <= cost < p.price_domain.upper and cost < p.demand.choke_price,
                "Feasible price domain and choke price checked",
            ),
        )

    def _solve(self, game: GameView, parameters: dict[str, JsonValue]) -> SolveResult:
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
        cost = params.marginal_costs[ids[0]]
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
