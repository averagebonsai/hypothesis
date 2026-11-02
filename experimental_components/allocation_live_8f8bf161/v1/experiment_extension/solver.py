from collections.abc import Sequence
from typing import ClassVar

from pydantic import JsonValue

from experiment_extension.game_view import AllocationGameView
from simulation_core.contracts import MethodContract, MethodRequirement, checked
from simulation_core.solver import Equilibrium, GameView, SolveResult, Solver
from simulation_core.types import Action


def project_simplex(target: Sequence[float], budget: float) -> list[float]:
    n = len(target)
    order = sorted(target, reverse=True)
    css = 0.0
    lam = 0.0
    for i, v in enumerate(order, start=1):
        css += v
        t = (css - budget) / i
        if i == n or order[i] <= t:
            lam = t
            break
    return [max(float(v) - float(lam), 0.0) for v in target]


class AllocationSolver(Solver):
    required_game_type: ClassVar[type[GameView] | None] = AllocationGameView
    result_certification: ClassVar[str] = "analytic"
    profile_domain: ClassVar[str] = "continuous"
    contract: ClassVar[MethodContract] = MethodContract(
        name="Simplex projection benchmark",
        requirements=(
            MethodRequirement(id="view", description="Game view available"),
            MethodRequirement(
                id="projection_inputs",
                description="Positive budget finite target dim ge 2",
            ),
        ),
        guarantees=["Euclidean projection of target onto simplex"],
        limitations=[
            "Analytic result for convex projection only",
            "Floating point tolerance applies",
        ],
    )

    def requirement_evidence(
        self, game: GameView, parameters: dict[str, JsonValue]
    ) -> tuple:
        ok_view = isinstance(game, AllocationGameView)
        proj_ok = False
        if ok_view:
            assert isinstance(game, AllocationGameView)
            try:
                b = game.budget()
                t = game.target()
                proj_ok = bool(b > 0 and len(t) >= 2 and all(v == v for v in t))
            except Exception:
                proj_ok = False
        return (
            checked("view", ok_view, "Game view capability checked", basis="runtime_check"),
            checked(
                "projection_inputs",
                proj_ok,
                "Positive budget finite target dim ge 2",
                basis="runtime_check",
            ),
        )

    def _solve(self, game: GameView, parameters: dict[str, JsonValue]) -> SolveResult:
        assert isinstance(game, AllocationGameView)
        budget = game.budget()
        target = game.target()
        alloc = project_simplex(target, budget)
        action = Action.model_validate(
            {"actor_id": game.actor_ids()[0], "kind": "allocate", "payload": {"allocation": alloc}}
        )
        outcome = game.evaluate([action])
        eq = Equilibrium(
            actions=(action,),
            outcome=outcome,
            regrets={game.actor_ids()[0]: 0.0},
        )
        return SolveResult(
            status="solved",
            certification="analytic",
            solution_concept="pure_nash",
            profile_domain="continuous",
            equilibria=(eq,),
            profiles_evaluated=1,
            total_profiles=1,
        )
