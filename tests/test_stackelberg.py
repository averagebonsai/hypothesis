import json
from math import isclose

import numpy as np
import pytest
from pydantic import ValidationError

from components.common.economics.models import LinearInverseDemand
from components.library import standard_registry
from components.mechanisms.stackelberg import (
    QuantityDomain,
    StackelbergGameView,
    StackelbergMechanism,
)
from components.protocols.sequential import DecisionPhase, SequentialParameters, SequentialProtocol
from components.solvers.stackelberg import StackelbergBackwardInductionSolver
from examples.stackelberg import (
    QuantityFirmInput,
    StackelbergInputs,
    build_experiment,
    fake_response,
    illustrative_inputs,
    run_job,
)
from simulation_core.benchmark import BenchmarkRunner
from simulation_core.execution import JobResult
from simulation_core.logging import replay
from simulation_core.model_gateway import FakeGateway
from simulation_core.runtime import SimulationRuntime
from simulation_core.types import Action, ObservationPermissions, WorldState


def profile(l, f, leader="Leader", follower="Follower"):
    return (
        Action(actor_id=leader, kind="set_quantity", payload={"quantity": float(l)}),
        Action(actor_id=follower, kind="set_quantity", payload={"quantity": float(f)}),
    )


def game_for(inputs=None):
    _, config = build_experiment(inputs or illustrative_inputs())
    state = WorldState(
        tick=0,
        phase="leader_commit",
        public=config.world.initial_public_state,
        private=config.world.initial_private_state,
    )
    return config, state, StackelbergGameView(config, state, StackelbergMechanism())


def test_two_commits_market_clearing_profile_assembly_and_analytical_benchmark():
    artifact = run_job()
    events = artifact.result.events
    assert artifact.result.status == "completed" and len(events) == 3
    assert events[1].actions[0].actor_id == "Leader"
    assert events[2].actions[0].actor_id == "Follower"
    assert events[1].state.phase == "follower_response" and events[2].state.phase == "finished"
    assert events[1].outcome.payoffs == {} and not events[1].outcome.metrics["market_complete"]
    assert "market_outcome" not in events[1].state.public
    assert events[2].outcome.payoffs == {"Leader": 900.0, "Follower": 600.0}
    report = artifact.benchmark
    assert report.result.status == "solved"
    assert report.result.solution_concept == "subgame_perfect"
    assert report.comparison_status == "complete"
    assert report.observed_source_ticks == {"Leader": 1, "Follower": 2}
    assert [a.payload["quantity"] for a in report.observed_actions] == [30.0, 20.0]
    eq = report.result.equilibria[0]
    assert [a.payload["quantity"] for a in eq.actions] == [40.0, 20.0]
    assert eq.outcome.metrics["price"] == 40.0
    assert eq.outcome.payoffs == {"Leader": 800.0, "Follower": 400.0}
    assert eq.regrets == {"Leader": 0.0, "Follower": 0.0}


def test_sequential_gain_is_not_simultaneous_fixed_follower_gain():
    artifact = run_job()
    report = artifact.benchmark
    # L=30 is a simultaneous best response to F=20. It is NOT the optimal commitment
    # against F's rational continuation: F*(30)=25 and the leader then earns 750.
    assert report.observed_regrets == {"Leader": 50.0, "Follower": 25.0}
    assert report.strategic_diagnostics["anticipated_leader_payoff"] == 750.0
    assert report.strategic_diagnostics["actual_leader_payoff"] == 900.0
    assert (
        report.strategic_diagnostics["anticipated_follower_at_observed_commitment"]["payload"][
            "quantity"
        ]
        == 25.0
    )
    assert "response curve" in report.deviation_interpretations["Leader"]


def test_follower_sees_actual_commitment_only_after_leader_and_private_state_is_isolated():
    gateway = FakeGateway(fake_response)
    artifact = run_job(gateway=gateway)
    assert len(gateway.requests) == 2
    leader, follower = [json.loads(req.input_json)["observation"] for req in gateway.requests]
    assert leader["phase"] == "leader_commit" and follower["phase"] == "follower_response"
    assert "commitments" not in leader["visible"]
    assert follower["visible"]["commitments"] == {"Leader": 30.0}
    assert "Follower" not in follower["visible"]["commitments"]
    assert leader["private"] == {"facts": {"own_marginal_cost": 20.0}, "memory": {}}
    assert follower["private"] == {"facts": {"own_marginal_cost": 20.0}, "memory": {}}
    assert all(d.rationale for event in artifact.result.events[1:] for d in event.decisions)
    calls = len(gateway.requests)
    assert replay(artifact.result.events)[-1] == artifact.result.final_state
    assert calls == len(gateway.requests)
    assert JobResult.model_validate_json(artifact.model_dump_json()) == artifact


def test_pure_evaluation_benchmark_independence_and_snapshot_aliases():
    config, state, game = game_for()
    before = (config.model_dump_json(), state.model_dump_json())
    for ql in [0, 20, 40, 80, 100]:
        leader = game.quantity_action("Leader", float(ql))
        game.evaluate((leader, game.follower_response(leader)))
    assert before == (config.model_dump_json(), state.model_dump_json())
    artifact = run_job()
    before = artifact.result.model_dump_json()
    report = BenchmarkRunner(standard_registry()).run(artifact.manifest.simulation, artifact.result)
    assert before == artifact.result.model_dump_json()
    report.observed_actions[0].payload["quantity"] = 99.0
    assert artifact.result.events[1].actions[0].payload["quantity"] == 30.0


@pytest.mark.parametrize(
    "a,b,c", [(100.0, 1.0, 20.0), (200.0, 2.0, 40.0), (20.0, 0.5, 3.0), (100.0, 1.0, 0.0)]
)
def test_textbook_equal_cost_interior_formula(a, b, c):
    upper = a / b * 2
    inputs = StackelbergInputs(
        demand=LinearInverseDemand(a=a, b=b),
        leader=QuantityFirmInput(
            id="L", marginal_cost=c, quantity_domain=QuantityDomain(upper=upper)
        ),
        follower=QuantityFirmInput(
            id="F", marginal_cost=c, quantity_domain=QuantityDomain(upper=upper)
        ),
    )
    _config, _state, game = game_for(inputs)
    solved = StackelbergBackwardInductionSolver().solve(game, {})
    assert solved.status == "solved"
    eq = solved.equilibria[0]
    assert isclose(eq.actions[0].payload["quantity"], (a - c) / (2 * b), abs_tol=1e-10)
    assert isclose(eq.actions[1].payload["quantity"], (a - c) / (4 * b), abs_tol=1e-10)
    assert isclose(eq.outcome.metrics["price"], (a + 3 * c) / 4, abs_tol=1e-10)


@pytest.mark.parametrize(
    "leader_upper,follower_lower,follower_upper,expected_l,expected_f",
    [
        (100.0, 0.0, 20.0, 30.0, 20.0),
        (25.0, 0.0, 100.0, 25.0, 27.5),
        (100.0, 35.0, 100.0, 22.5, 35.0),
    ],
)
def test_bounded_backward_induction_accounts_for_changed_follower_curve(
    leader_upper, follower_lower, follower_upper, expected_l, expected_f
):
    inputs = StackelbergInputs(
        demand=LinearInverseDemand(a=100.0, b=1.0),
        leader=QuantityFirmInput(
            id="Leader", marginal_cost=20.0, quantity_domain=QuantityDomain(upper=leader_upper)
        ),
        follower=QuantityFirmInput(
            id="Follower",
            marginal_cost=20.0,
            quantity_domain=QuantityDomain(lower=follower_lower, upper=follower_upper),
        ),
    )
    _, _, game = game_for(inputs)
    eq = StackelbergBackwardInductionSolver().solve(game, {}).equilibria[0]
    assert [a.payload["quantity"] for a in eq.actions] == [expected_l, expected_f]


def test_follower_response_and_leader_optimum_dominate_independent_dense_grid():
    inputs = StackelbergInputs(
        demand=LinearInverseDemand(a=100.0, b=1.0),
        leader=QuantityFirmInput(
            id="Leader", marginal_cost=10.0, quantity_domain=QuantityDomain(upper=100.0)
        ),
        follower=QuantityFirmInput(
            id="Follower", marginal_cost=30.0, quantity_domain=QuantityDomain(upper=100.0)
        ),
    )
    _, _, game = game_for(inputs)
    solved = StackelbergBackwardInductionSolver().solve(game, {})
    eq = solved.equilibria[0]
    assert [a.payload["quantity"] for a in eq.actions] == [55.0, 7.5]
    best_leader = eq.outcome.payoffs["Leader"]
    for quantity in np.linspace(0, 100, 501):
        action = game.quantity_action("Leader", float(quantity))
        reply = game.follower_response(action)
        value = game.evaluate((action, reply)).payoffs["Leader"]
        assert value <= best_leader + 1e-9
    for ql in [0.0, 20.0, 55.0, 90.0, 100.0]:
        leader = game.quantity_action("Leader", ql)
        reply = game.follower_response(leader)
        expected = game.evaluate((leader, reply)).payoffs["Follower"]
        assert all(
            game.evaluate(profile(ql, float(qf))).payoffs["Follower"] <= expected + 1e-9
            for qf in np.linspace(0, 100, 501)
        )


def test_quantity_bound_schema_and_out_of_turn_fail_before_transition():
    config, state, _game = game_for()
    mechanism = StackelbergMechanism()
    for invalid in (
        profile(30, 20)[1:],
        profile(30, 20),
        profile(101, 20)[:1],
        (Action(actor_id="Leader", kind="set_quantity", payload={"quantity": -1.0}),),
    ):
        with pytest.raises(ValueError):
            mechanism.validate_actions(config.world, state, invalid)
    transition = mechanism.transition(config.world, state, profile(30, 20)[:1])
    after = WorldState(
        tick=1, phase="follower_response", public=transition.public, private=state.private
    )
    with pytest.raises(ValueError):
        mechanism.validate_actions(config.world, after, profile(30, 20)[:1])
    for value in (float("inf"), float("nan"), "20", True):
        with pytest.raises(ValueError):
            mechanism.evaluate(
                config.world,
                state,
                (
                    Action(actor_id="Leader", kind="set_quantity", payload={"quantity": value}),
                    profile(30, 20)[1],
                ),
            )


def test_step_limit_preserves_leader_commitment_without_fabricating_follower_or_payoffs():
    inputs = illustrative_inputs().model_copy(update={"max_steps": 1})
    gateway = FakeGateway(fake_response)
    artifact = run_job(inputs, gateway=gateway)
    assert len(gateway.requests) == 1
    assert artifact.result.status == "step_limit"
    assert artifact.result.final_state.public["commitments"] == {"Leader": 30.0}
    assert artifact.result.outcomes[-1].payoffs == {}
    assert artifact.benchmark.result.status == "solved"
    assert artifact.benchmark.comparison_status == "incomplete"
    assert not artifact.benchmark.comparisons
    assert not artifact.benchmark.observed_regrets
    assert artifact.benchmark.observed_source_ticks == {"Leader": 1}


def test_seeded_future_commitments_and_invalid_state_transitions_rejected():
    config, state, _game = game_for()
    bad = state.model_copy(update={"public": {**state.public, "commitments": {"Follower": 20.0}}})
    with pytest.raises(ValueError, match="history"):
        StackelbergMechanism().validate_state(config.world, bad)
    bad = state.model_copy(update={"public": {**state.public, "market_outcome": {}}})
    with pytest.raises(ValueError, match="before"):
        StackelbergMechanism().validate_state(config.world, bad)


def test_zero_price_ties_and_continuous_leader_multiplicity_are_explicit():
    inputs = StackelbergInputs(
        demand=LinearInverseDemand(a=100.0, b=1.0),
        leader=QuantityFirmInput(
            id="Leader", marginal_cost=0.0, quantity_domain=QuantityDomain(upper=100.0)
        ),
        follower=QuantityFirmInput(
            id="Follower",
            marginal_cost=0.0,
            quantity_domain=QuantityDomain(lower=200.0, upper=300.0),
        ),
    )
    _, _, game = game_for(inputs)
    solved = StackelbergBackwardInductionSolver().solve(game, {})
    assert solved.status == "multiple"
    assert solved.diagnostics["optimal_leader_intervals"] == [[0.0, 100.0]]
    assert all(eq.actions[1].payload["quantity"] == 200.0 for eq in solved.equilibria)


def test_sequential_protocol_is_generic_and_checks_references_and_phase_permissions():
    from examples.measurements import run_job as measurement_job

    base = measurement_job().manifest.simulation
    ids = tuple(actor.id for actor in base.world.actors)
    schedule = SequentialParameters(
        phases=(
            DecisionPhase(name="first", actor_ids=(ids[0],)),
            DecisionPhase(name="second", actor_ids=ids[1:]),
        )
    )
    config = base.model_copy(
        update={
            "protocol_id": "sequential.v1",
            "protocol_parameters": schedule.model_dump(mode="json"),
            "assumptions": (),
            "benchmark": None,
        }
    )
    result = SimulationRuntime(standard_registry()).run(config)
    assert (
        result.status == "completed"
        and len(result.events[1].actions) == 1
        and len(result.events[2].actions) == 2
    )
    invalid = SequentialParameters(phases=(DecisionPhase(name="first", actor_ids=("unknown",)),))
    with pytest.raises(ValueError, match="Unknown actor"):
        SequentialProtocol(invalid.model_dump(mode="json")).validate_config(config.world)
    wrong = config.model_copy(
        update={"phase_permissions": {"typo": {ids[0]: ObservationPermissions()}}}
    )
    with pytest.raises(ValueError, match="Unknown phase"):
        SimulationRuntime(standard_registry()).run(wrong)


def test_invalid_schedule_and_user_role_inputs_fail_validation():
    for phases in (
        (DecisionPhase(name="x", actor_ids=("a",)), DecisionPhase(name="x", actor_ids=("b",))),
        (DecisionPhase(name="finished", actor_ids=("a",)),),
    ):
        with pytest.raises(ValidationError):
            SequentialParameters(phases=phases)
    with pytest.raises(ValidationError):
        DecisionPhase(name="x", actor_ids=("a", "a"))
    inputs = illustrative_inputs()
    with pytest.raises(ValidationError):
        StackelbergInputs(demand=inputs.demand, leader=inputs.leader, follower=inputs.leader)
    assert StackelbergInputs.model_validate_json(inputs.model_dump_json()) == inputs


def test_profile_assembly_rejects_reversed_or_missing_stages():
    artifact = run_job()
    _, _, game = game_for()
    events = artifact.result.events
    with pytest.raises(ValueError):
        game.observed_profile((events[0], events[2]), 2)
    invalid = events[1].model_copy(update={"actions": events[2].actions})
    with pytest.raises(ValueError):
        game.observed_profile((events[0], invalid, events[2]), 2)


@pytest.mark.parametrize(
    "lower,cost,expected_quantity,expected_profit",
    [
        (0.0, 150.0, 0.0, 0.0),
        (90.0, 20.0, 90.0, -900.0),
    ],
)
def test_shutdown_and_forced_loss_are_preserved(lower, cost, expected_quantity, expected_profit):
    inputs = illustrative_inputs()
    inputs = inputs.model_copy(
        update={
            "leader": inputs.leader.model_copy(
                update={
                    "marginal_cost": cost,
                    "quantity_domain": QuantityDomain(lower=lower, upper=100.0),
                }
            )
        }
    )
    _, _, game = game_for(inputs)
    equilibrium = StackelbergBackwardInductionSolver().solve(game, {}).equilibria[0]
    assert equilibrium.actions[0].payload["quantity"] == expected_quantity
    assert equilibrium.outcome.payoffs["Leader"] == expected_profit


def test_comparison_at_first_commit_uses_only_available_actions():
    artifact = run_job()
    config = artifact.manifest.simulation
    config = config.model_copy(
        update={
            "benchmark": config.benchmark.model_copy(update={"comparison_tick": 1}),
            "assumptions": (),
        }
    )
    report = BenchmarkRunner(standard_registry()).run(config, artifact.result)
    assert report.result.status == "solved"
    assert report.comparison_status == "incomplete"
    assert report.observed_source_ticks == {"Leader": 1}
    assert len(report.observed_actions) == 1
    assert report.comparisons == () and report.observed_regrets == {}
