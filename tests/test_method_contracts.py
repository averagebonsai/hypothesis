"""Required assumptions are executable guards; empirical support is not a proof."""

import subprocess
import sys

import pytest
from pydantic import ValidationError

from components.common.math.scalar import (
    SCALAR_SEARCH_CONTRACT,
    ScalarSearchSettings,
    maximize_scalar,
)
from components.library import standard_registry
from components.mechanisms.bertrand import BertrandGameView, HomogeneousBertrandMechanism
from components.mechanisms.normal_form import NormalFormGameView, PayoffMatrixMechanism
from components.solvers.bertrand import TextbookBertrandSolver
from components.solvers.numerical_nash import NumericalNashSolver
from components.solvers.pure_nash import PureNashSolver
from examples.bertrand import build_experiment as bertrand_config
from examples.llm_payoff_matrix import run_llm_job
from examples.payoff_matrix import build_experiment as matrix_config
from simulation_core.contracts import (
    ApplicabilityError,
    MethodContract,
    MethodRequirement,
    RequirementEvidence,
    checked,
)
from simulation_core.solver import Solver, SolveResult
from simulation_core.validation import initial_state


def bertrand_game(config=None):
    config = config or bertrand_config()
    registry = standard_registry()
    protocol = registry.protocols[config.protocol_id](config.protocol_parameters)
    return BertrandGameView(config, initial_state(config, protocol), HomogeneousBertrandMechanism())


def matrix_game():
    config, registry = matrix_config()
    protocol = registry.protocols[config.protocol_id](config.protocol_parameters)
    return NormalFormGameView(config, initial_state(config, protocol), PayoffMatrixMechanism())


def test_solver_catalog_lists_requirements_guarantees_and_limits():
    catalog = standard_registry().describe()["solver_contracts"]
    assert set(catalog) == {
        "pure_nash.v1",
        "textbook_bertrand.v1",
        "backward_induction.v1",
        "numerical_nash.v1",
    }
    for value in catalog.values():
        contract = MethodContract.from_json_values(value)
        assert contract.requirements and contract.guarantees and contract.limitations
    assert "global" in " ".join(catalog["numerical_nash.v1"]["limitations"])


def test_theorem_conditions_are_checked_without_evaluating_payoffs(monkeypatch):
    game = bertrand_game()
    monkeypatch.setattr(
        game, "evaluate", lambda _: pytest.fail("Assessment must not solve the game")
    )
    report = TextbookBertrandSolver().assess(game, {})
    checks = {item.requirement_id: item for item in report.evidence}
    assert checks["equal_cost_duopoly"].status == "verified"
    assert checks["homogeneous_rules"].basis == "model_definition"
    assert checks["pure_payoffs"].status == "unverified"
    assert report.can_execute and not report.preconditions_verified
    with pytest.raises(ApplicabilityError, match="pure_payoffs"):
        report.require_preconditions()
    assert type(report).model_validate_json(report.model_dump_json()) == report


def test_violated_theorem_requirement_blocks_direct_solving():
    base = bertrand_config()
    parameters = {**base.world.parameters, "marginal_costs": {"A": 20.0, "B": 25.0}}
    game = bertrand_game(
        base.model_copy(
            update={
                "assumptions": (),
                "world": base.world.model_copy(update={"parameters": parameters}),
            }
        )
    )
    result = TextbookBertrandSolver().solve(game, {})
    assert result.status == "unsupported" and result.equilibria == ()
    assert not result.applicability.can_execute
    assert (
        next(
            e for e in result.applicability.evidence if e.requirement_id == "equal_cost_duopoly"
        ).status
        == "violated"
    )


def test_budget_exhaustion_retains_assessments_without_claiming_nonexistence():
    result = PureNashSolver().solve(matrix_game(), {"max_profiles": 1})
    assert result.status == "budget_exhausted" and result.applicability.can_execute
    assert (
        next(
            e for e in result.applicability.evidence if e.requirement_id == "enumeration_budget"
        ).status
        == "violated"
    )
    assert SolveResult.model_validate_json(result.model_dump_json()) == result


def test_benchmark_result_retains_method_contract():
    artifact = run_llm_job()
    result = artifact.benchmark.result
    assert result.applicability.contract.name == PureNashSolver.contract.name
    assert type(artifact).model_validate_json(artifact.model_dump_json()) == artifact


def test_registry_can_assess_configured_theorem_without_actor_calls():
    from examples.stackelberg import build_experiment, fake_response, illustrative_inputs
    from simulation_core.model_gateway import FakeGateway

    _, config = build_experiment(illustrative_inputs())
    gateway = FakeGateway(fake_response)
    report = standard_registry(gateway).benchmark_applicability(config)
    assert report.can_execute and gateway.requests == []
    assert (
        next(e for e in report.evidence if e.requirement_id == "continuation_rule").basis
        == "model_definition"
    )


def test_inherited_view_type_does_not_automatically_certify_theorem_rules():
    class CustomView(BertrandGameView):
        pass

    game = bertrand_game()
    custom = CustomView(game.config, game.state, game.mechanism)
    result = TextbookBertrandSolver().solve(custom, {})
    assert result.status == "unsupported"
    assert (
        next(
            e for e in result.applicability.evidence if e.requirement_id == "homogeneous_rules"
        ).status
        == "unverified"
    )


def test_unknown_required_convexity_blocks_future_solver_before_search():
    class FutureConvexSolver(Solver):
        contract = MethodContract(
            name="Example convex method",
            requirements=(
                MethodRequirement(id="view", description="A game view"),
                MethodRequirement(
                    id="convex", description="Convex objective over a convex feasible set"
                ),
            ),
        )

        def _solve(self, game, parameters):
            pytest.fail("Unknown convexity must block execution")

    result = FutureConvexSolver().solve(matrix_game(), {})
    assert result.status == "unsupported"
    with pytest.raises(ApplicabilityError, match="convex"):
        result.applicability.require_execution()


@pytest.mark.parametrize("basis", ["sampled_test", "declaration", "none"])
def test_sampled_or_declared_properties_cannot_be_promoted_to_proofs(basis):
    with pytest.raises(ValidationError, match="cannot verify"):
        RequirementEvidence(
            requirement_id="convex",
            status="verified",
            basis=basis,
            explanation="The sampled Hessians were positive",
        )
    supported = RequirementEvidence(
        requirement_id="convex",
        status="unverified",
        basis=basis,
        explanation="No proof over the full domain",
    )
    assert supported.status == "unverified"


def test_sampled_counterexample_may_refute_a_property():
    contract = MethodContract(
        name="Convex requirement",
        requirements=(MethodRequirement(id="convex", description="Global convexity"),),
    )
    report = contract.assess(
        (
            RequirementEvidence(
                requirement_id="convex",
                status="violated",
                basis="sampled_test",
                explanation="A feasible counterexample violates the convexity inequality",
            ),
        )
    )
    assert not report.can_execute


def test_contract_rejects_mislabeled_or_duplicate_evidence():
    contract = MethodContract(
        name="Test", requirements=(MethodRequirement(id="x", description="Condition x"),)
    )
    evidence = checked("other", True, "Mismatched requirement")
    with pytest.raises(ValueError):
        contract.assess((evidence,))
    evidence = checked("x", True, "Checked")
    with pytest.raises(ValueError):
        contract.assess((evidence, evidence))


def test_numerical_method_does_not_claim_convexity_or_global_optimality():
    from components.mechanisms.differentiated_bertrand import (
        DifferentiatedBertrandGameView,
        DifferentiatedBertrandMechanism,
    )
    from examples.differentiated_bertrand import build_experiment, illustrative_inputs

    _, config = build_experiment(illustrative_inputs())
    registry = standard_registry()
    protocol = registry.protocols[config.protocol_id](config.protocol_parameters)
    game = DifferentiatedBertrandGameView(
        config, initial_state(config, protocol), DifferentiatedBertrandMechanism()
    )
    report = NumericalNashSolver().assess(game, {})
    checks = {item.requirement_id: item for item in report.evidence}
    assert report.can_execute and not report.preconditions_verified
    assert checks["finite_scalar_boxes"].status == "verified"
    assert checks["correct_smooth_gradients"].status == "unverified"


def test_scalar_contract_distinguishes_checked_samples_from_unknown_global_properties():
    result = maximize_scalar(lambda x: -((x - 1) ** 2), (0.0, 2.0), ScalarSearchSettings(), 0.0)
    assert result.applicability.contract == SCALAR_SEARCH_CONTRACT
    checks = {item.requirement_id: item for item in result.applicability.evidence}
    assert checks["finite_samples"].status == "verified"
    assert checks["pure_objective"].status == "unverified"
    assert checks["local_regularity"].status == "unverified"
    with pytest.raises(ApplicabilityError):
        maximize_scalar(
            lambda _: pytest.fail("Must fail before objective evaluation"),
            (2.0, 1.0),
            ScalarSearchSettings(),
            1.0,
        )


def test_execution_guard_remains_active_under_python_optimization():
    code = """from simulation_core.contracts import MethodContract, MethodRequirement, ApplicabilityError
report = MethodContract(name="Test", requirements=(MethodRequirement(id="convex", description="Convexity"),)).assess()
try:
    report.require_execution()
except ApplicabilityError:
    print("blocked")
else:
    raise RuntimeError("Guard was optimized away")
"""
    result = subprocess.run(
        [sys.executable, "-O", "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "blocked"


def test_solver_failure_keeps_applicability_and_does_not_assert_a_guarantee(monkeypatch):
    game = matrix_game()

    def failure(profile):
        raise ArithmeticError("Invalid payoff evaluation")

    monkeypatch.setattr(game, "evaluate", failure)
    result = PureNashSolver().solve(game, {})
    assert result.status == "failed" and result.applicability is not None
    assert result.applicability.can_execute and not result.applicability.preconditions_verified
    assert result.diagnostics["error_category"] == "ArithmeticError"


def test_scalar_contract_rejects_overflowing_interval_width():
    from components.common.math.scalar import assess_scalar_search

    report = assess_scalar_search((-1e308, 1e308), 0.0)
    assert not report.can_execute
    assert (
        next(item for item in report.evidence if item.requirement_id == "bounds").status
        == "violated"
    )
