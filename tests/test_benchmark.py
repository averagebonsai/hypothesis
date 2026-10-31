from copy import deepcopy
from itertools import product

from components.games.normal_form import NormalFormGameView
from components.mechanisms.normal_form import PayoffMatrixMechanism
from components.solvers.pure_nash import PureNashSolver
from examples.llm_payoff_matrix import run_llm_job
from examples.payoff_matrix import build_experiment
from simulation_core.benchmark import BenchmarkRunner
from simulation_core.runtime import SimulationRuntime
from simulation_core.types import BenchmarkSpec


def benchmark_fixture():
    config, registry = build_experiment()
    config = config.model_copy(
        update={"benchmark": BenchmarkSpec(solver_id="pure_nash.v1", game_view_id="normal_form.v1")}
    )
    run = SimulationRuntime(registry).run(config)
    return config, registry, run


def test_prisoners_dilemma_equilibrium_deviations_and_purity():
    config, registry, run = benchmark_fixture()
    before = (config.model_dump_json(), run.model_dump_json())
    report = BenchmarkRunner(registry).run(config, run)
    assert report.result.status == "solved"
    assert report.result.profiles_evaluated == 4
    equilibrium = report.result.equilibria[0]
    assert [action.payload["move"] for action in equilibrium.actions] == ["defect", "defect"]
    assert equilibrium.outcome.payoffs == {"A": 1.0, "B": 1.0}
    assert report.comparisons[0].payoff_deltas == {"A": -1.0, "B": 4.0}
    assert report.comparisons[0].action_differences == {"A": True, "B": False}
    assert report.observed_regrets == {"A": 1.0, "B": 0.0}
    assert before == (config.model_dump_json(), run.model_dump_json())


def matrix_game(values):
    config, _registry, run = benchmark_fixture()
    params = deepcopy(config.world.parameters)
    params["cells"] = [
        {"moves": {"A": a, "B": b}, "payoffs": {"A": x, "B": y}}
        for (a, b), (x, y) in zip(product(["cooperate", "defect"], repeat=2), values)
    ]
    config = config.model_copy(
        update={"assumptions": (), "world": config.world.model_copy(update={"parameters": params})}
    )
    return NormalFormGameView(config, run.events[0].state, PayoffMatrixMechanism())


def test_matching_pennies_has_no_pure_equilibrium():
    game = matrix_game([(1.0, -1.0), (-1.0, 1.0), (-1.0, 1.0), (1.0, -1.0)])
    result = PureNashSolver().solve(game, {})
    assert result.status == "no_pure_equilibrium"
    assert result.equilibria == ()
    assert "mixed" in result.diagnostics["scope"]


def test_coordination_game_lists_both_equilibria():
    game = matrix_game([(2.0, 2.0), (0.0, 0.0), (0.0, 0.0), (1.0, 1.0)])
    result = PureNashSolver().solve(game, {})
    assert result.status == "multiple" and len(result.equilibria) == 2
    assert all(max(item.regrets.values()) == 0.0 for item in result.equilibria)


def test_budget_exhaustion_does_not_invalidate_primary_run():
    artifact = run_llm_job(max_profiles=1)
    assert artifact.result.status == "completed"
    assert artifact.benchmark.result.status == "budget_exhausted"
    assert artifact.benchmark.comparisons == ()
    assert artifact.benchmark.result.profiles_evaluated == 0


def test_benchmark_failure_is_separate_and_does_not_change_actor_results():
    config, registry, run = benchmark_fixture()

    class FailingSolver(PureNashSolver):
        def solve(self, game, parameters):
            raise ArithmeticError("test failure")

    registry.solvers["pure_nash.v1"] = FailingSolver
    report = BenchmarkRunner(registry).run(config, run)
    assert report.result.status == "failed"
    assert report.result.diagnostics["error_category"] == "ArithmeticError"
    assert run.status == "completed"


def test_explicit_compared_tick_and_all_equilibrium_comparisons():
    config, registry = build_experiment(rounds=2)
    config = config.model_copy(
        update={
            "benchmark": BenchmarkSpec(
                solver_id="pure_nash.v1", game_view_id="normal_form.v1", comparison_tick=1
            )
        }
    )
    run = SimulationRuntime(registry).run(config)
    report = BenchmarkRunner(registry).run(config, run)
    assert report.comparison_tick == 1
    assert len(report.config_sha256) == 64
    config = config.model_copy(
        update={"benchmark": config.benchmark.model_copy(update={"comparison_tick": 99})}
    )
    assert BenchmarkRunner(registry).run(config, run).result.status == "failed"


def test_comparison_retains_every_equilibrium_without_selecting_one():
    game = matrix_game([(2.0, 2.0), (0.0, 0.0), (0.0, 0.0), (1.0, 1.0)])
    from components.library import standard_registry

    registry = standard_registry()
    run = SimulationRuntime(registry).run(game.config)
    report = BenchmarkRunner(registry).run(game.config, run)
    assert report.result.status == "multiple"
    assert [comparison.equilibrium_index for comparison in report.comparisons] == [0, 1]
