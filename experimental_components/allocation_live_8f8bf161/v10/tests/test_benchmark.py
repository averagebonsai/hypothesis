from experiment_extension.game_view import AllocationGameView
from experiment_extension.mechanism import AllocationMechanism
from experiment_extension.solver import AllocationSolver

from agent_tools.verification import independent_optimum
from simulation_core.problems import (
    ConstraintSpec,
    ObjectiveSpec,
    Operation,
    ProblemActor,
    ProblemStatement,
    Reference,
    VariableSpec,
)
from simulation_core.types import Action, SimulationConfig, WorldState


def _simconfig():
    return SimulationConfig.model_validate(
        {
            "schema_version": "simulation.config.v1",
            "world": {
                "actors": [
                    {
                        "id": "allocator",
                        "kind": "allocator",
                        "action_space": {"schemas": {"allocate": "experimental.allocation_live_8f8bf161.action"}},
                        "policy_id": "scripted.v1",
                        "policy_parameters": {"kind": "allocate", "payload": {"allocation": [5.0, 5.0]}},
                    }
                ],
                "parameters": {"budget": 10.0, "target": [8.0, 6.0]},
                "initial_public_state": {"budget": 10.0, "target": [8.0, 6.0]},
            },
            "mechanism_id": "experimental.allocation_live_8f8bf161.mechanism",
            "protocol_id": "simultaneous.v1",
            "protocol_parameters": {"rounds": 1},
        }
    )


def _view():
    cfg = _simconfig()
    st = WorldState.model_validate({"tick": 0, "phase": "act", "public": {"budget": 10.0, "target": [8.0, 6.0]}, "private": {}})
    return AllocationGameView(cfg, st, AllocationMechanism())


def _problem():
    diff = Operation(operator="subtract", arguments=(Reference(name="allocation"), Reference(name="target")))
    sq = Operation(operator="square", arguments=(diff,))
    total = Operation(operator="sum", arguments=(sq,))
    neg = Operation(operator="negate", arguments=(total,))
    alloc = Operation(operator="sum", arguments=(Reference(name="allocation"),))
    return ProblemStatement(description="d", actors=(ProblemActor(id="allocator"),), parameters={"budget": 10.0, "target": (8.0, 6.0)}, variables=(VariableSpec(name="allocation", actor_id="allocator", shape="vector", dimension="target", domain="continuous", lower=0.0),), objectives=(ObjectiveSpec(name="score", actor_id="allocator", sense="maximize", expression=neg),), constraints=(ConstraintSpec(name="fixed_budget", left=alloc, relation="eq", right=Reference(name="budget")),))


def _action(alloc):
    return Action.model_validate({"actor_id": "allocator", "kind": "allocate", "payload": {"allocation": alloc}})


def test_game_view_evaluates():
    view = _view()
    assert view.actor_ids() == ("allocator",)
    out = view.evaluate([_action([5.0, 5.0])])
    assert abs(out.payoffs["allocator"] - (-18.0)) < 1e-9


def test_solver_fixture_optimum():
    result = AllocationSolver().solve(_view(), {})
    assert result.status == "solved"
    alloc = result.equilibria[0].actions[0].payload["allocation"]
    assert abs(alloc[0] - 6.0) < 1e-6 and abs(alloc[1] - 4.0) < 1e-6
    assert abs(result.equilibria[0].outcome.payoffs["allocator"] - (-8.0)) < 1e-6


def test_solver_matches_reference():
    view = _view()
    result = AllocationSolver().solve(view, {})
    alloc = tuple(result.equilibria[0].actions[0].payload["allocation"])
    payoff = result.equilibria[0].outcome.payoffs["allocator"]
    ref = independent_optimum(_problem(), {"allocation": alloc})
    assert abs(payoff - (-8.0)) < 1e-4
    assert abs(ref - (-8.0)) < 1e-4
    assert abs(payoff - ref) < 1e-4
