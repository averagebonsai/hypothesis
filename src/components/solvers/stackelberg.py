"""Exact piecewise-quadratic backward induction with bounded quantity domains."""

from itertools import pairwise

from pydantic import Field, JsonValue

from components.mechanisms.stackelberg import StackelbergGameView
from simulation_core.solver import Equilibrium, GameView, Solver, SolveResult
from simulation_core.types import FrozenModel


class BackwardInductionParameters(FrozenModel):
    payoff_tolerance: float = Field(default=1e-9, ge=0)


class StackelbergBackwardInductionSolver(Solver):
    required_game_type = StackelbergGameView

    def solve(self, game: GameView, parameters: dict[str, JsonValue]) -> SolveResult:
        settings = BackwardInductionParameters.from_json_values(parameters)
        if not isinstance(game, StackelbergGameView):
            return SolveResult(
                solution_concept="subgame_perfect",
                status="unsupported",
                profile_domain="continuous",
                profiles_evaluated=None,
                total_profiles=None,
                diagnostics={"reason": "Linear quantity-leadership view required"},
            )
        p = game.parameters
        leader, follower = game.leader_id(), game.follower_id()
        ld, fd = p.quantity_domains[leader], p.quantity_domains[follower]
        scale = p.demand.choke_quantity - p.marginal_costs[follower] / p.demand.b
        cuts = sorted(
            {
                ld.lower,
                ld.upper,
                *[
                    value
                    for value in (scale - 2 * fd.lower, scale - 2 * fd.upper)
                    if ld.lower < value < ld.upper
                ],
            }
        )
        candidates = set(cuts)
        zero_intervals = []
        for low, high in pairwise(cuts):
            midpoint = low + (high - low) / 2
            raw = (scale - midpoint) / 2
            if raw <= fd.lower:
                intercept = p.demand.a - p.demand.b * fd.lower
                slope = p.demand.b
            elif raw >= fd.upper:
                intercept = p.demand.a - p.demand.b * fd.upper
                slope = p.demand.b
            else:
                intercept = p.demand.a - p.demand.b * (scale / 2)
                slope = p.demand.b / 2
            stationary = (intercept / 2 - p.marginal_costs[leader] / 2) / slope
            candidates.add(min(max(stationary, low), high))
            choke = intercept / slope
            if low <= choke <= high:
                candidates.add(choke)
            if p.marginal_costs[leader] == 0.0 and high > max(low, choke):
                zero_intervals.append([max(low, choke), high])
        evaluated = []
        for quantity in sorted(candidates):
            action = game.quantity_action(leader, quantity)
            reply = game.follower_response(action)
            outcome = game.evaluate((action, reply))
            evaluated.append((action, reply, outcome))
        optimum = max(item[2].payoffs[leader] for item in evaluated)
        equilibria = []
        for action, reply, outcome in evaluated:
            if optimum - outcome.payoffs[leader] <= settings.payoff_tolerance:
                eq = Equilibrium(actions=(action, reply), outcome=outcome, regrets={})
                gains = game.strategic_deviations(eq.actions, (eq,)).gains
                gains[leader] = max(0.0, optimum - outcome.payoffs[leader])
                equilibria.append(eq.model_copy(update={"regrets": gains}))
        intervals = zero_intervals if optimum == 0.0 else []
        return SolveResult(
            solution_concept="subgame_perfect",
            status="multiple" if len(equilibria) > 1 or intervals else "solved",
            equilibria=tuple(equilibria),
            profile_domain="continuous",
            profiles_evaluated=len(evaluated),
            total_profiles=None,
            diagnostics={
                "method": "Piecewise quadratic leader optimization along the bounded follower best-response curve",
                "payoff_tolerance": settings.payoff_tolerance,
                "follower_strategy": "clip((a-c_F-b*q_L)/(2*b), follower_lower, follower_upper); choose smallest quantity on zero-profit ties",
                "leader_bounds": ld.model_dump(mode="json"),
                "follower_bounds": fd.model_dump(mode="json"),
                "candidate_leader_quantities": [q for q in sorted(candidates)],
                "optimal_leader_intervals": [[q for q in interval] for interval in intervals],
                "candidate_payoffs": [
                    {
                        "quantity": action.payload["quantity"],
                        "leader_profit": outcome.payoffs[leader],
                        "follower_quantity": reply.payload["quantity"],
                    }
                    for action, reply, outcome in evaluated
                ],
                "scope": "Single two-firm quantity game, truncated linear inverse demand, nonnegative constant costs, bounded commitments; fixed minimum-quantity follower tie-breaking",
                "multiplicity": "All maximizing analytic candidates retained; optimal zero-profit intervals represent continuous multiplicity, not an exhaustive enumeration of follower strategies",
            },
        )
