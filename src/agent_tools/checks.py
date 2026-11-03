"""Optional, capability-scoped behavioral checks; experiment rules determine validity."""

from abc import ABC, abstractmethod
from copy import deepcopy

from simulation_core.execution import JobResult
from simulation_core.problems import Numeric, ProblemStatement
from simulation_core.registry import ComponentRegistry
from simulation_core.types import Action, SimulationConfig, WorldState

from .specs import VerificationFinding, VerificationSpec
from .verification import assignments_for, independent_optimum, verify_profile


class VerificationCheck(ABC):
    """Template for custom experiment checks, executed only by the isolated worker.

    An agent-authored check is not automatically an independent reference. Report
    its evidence and applicability, including unsupported/unverified outcomes.
    """

    @abstractmethod
    def assess(self, artifact: JobResult, registry: ComponentRegistry) -> VerificationFinding: ...


def actions_for(
    profile: tuple[Action, ...],
    assignments: dict[str, Numeric],
    spec: VerificationSpec,
) -> tuple[Action, ...]:
    payloads = {action.actor_id: deepcopy(action.payload) for action in profile}
    for binding in spec.variables:
        value = assignments[binding.variable]
        payloads[binding.actor_id][binding.payload_field] = (
            list(value) if isinstance(value, tuple) else value
        )
    return tuple(
        action.model_copy(update={"payload": payloads[action.actor_id]}) for action in profile
    )


def validate_profile(
    registry: ComponentRegistry,
    config: SimulationConfig,
    state: WorldState,
    profile: tuple[Action, ...],
) -> None:
    import json

    actors = {actor.id: actor for actor in config.world.actors}
    protocol = registry.protocols[config.protocol_id](dict(config.protocol_parameters))
    expected = set(
        protocol.active_actor_ids(config.world.model_copy(deep=True), state.model_copy(deep=True))
    )
    if {a.actor_id for a in profile} != expected or len(profile) != len(expected):
        raise ValueError("Behavior check requires exactly the active actor profile")
    for action in profile:
        actor = actors[action.actor_id]
        schema_id = actor.action_space.schemas[action.kind]
        registry.action_schemas[schema_id].model_validate_json(
            json.dumps(action.payload, allow_nan=False)
        )
    protocol.validate_action_batch(
        config.world.model_copy(deep=True), state.model_copy(deep=True), profile
    )
    mechanism = registry.mechanisms[config.mechanism_id]()
    mechanism.validate_actions(
        config.world.model_copy(deep=True),
        state.model_copy(deep=True),
        tuple(a.model_copy(deep=True) for a in profile),
    )


def invalid_assignments(
    problem: ProblemStatement, seed: dict[str, Numeric]
) -> list[dict[str, Numeric]]:
    """Finite counterexamples derived from declared bounds/constraints, not domain guesses."""
    candidates = []
    for variable in problem.variables:
        value = seed[variable.name]
        coordinates = value if isinstance(value, tuple) else (value,)
        for index, coordinate in enumerate(coordinates):
            changes = [
                coordinate + max(1.0, abs(coordinate)),
                coordinate - max(1.0, abs(coordinate)),
            ]
            for bound, sign in ((variable.lower, -1), (variable.upper, 1)):
                if bound is not None:
                    limit = bound[index] if isinstance(bound, tuple) else bound
                    changes.append(limit + sign * max(1.0, abs(limit)))
            for changed in changes:
                values = list(coordinates)
                values[index] = changed
                assignment = {
                    **seed,
                    variable.name: tuple(values) if variable.shape == "vector" else changed,
                }
                if not problem.evaluate(assignment).feasible:
                    candidates.append(assignment)
    return candidates


def standard_checks(
    artifact: JobResult,
    registry: ComponentRegistry,
    spec: VerificationSpec | None,
) -> tuple[VerificationFinding, ...]:
    problem = artifact.manifest.request.problem
    if problem is None or spec is None:
        return (
            VerificationFinding(
                id="numeric_behavior",
                status="unsupported",
                evidence="No structured numeric problem/bindings",
                required=False,
            ),
        )
    if problem.evaluation != "deterministic":
        return (
            VerificationFinding(
                id="numeric_behavior",
                status="unsupported",
                evidence="Use a stochastic/domain-specific checker",
                required=spec.action_behavior == "reject_infeasible",
            ),
        )
    config = artifact.manifest.simulation
    committed = [event for event in artifact.result.events if event.kind == "committed"]
    if not committed:
        return (
            VerificationFinding(
                id="numeric_behavior",
                status="unsupported",
                evidence="No committed profile available",
                required=True,
            ),
        )
    event = committed[0]
    profile = event.actions
    state = artifact.result.events[0].state
    if {a.actor_id for a in profile} != {binding.actor_id for binding in spec.variables}:
        return (
            VerificationFinding(
                id="numeric_behavior",
                status="unsupported",
                evidence="Default checker needs a complete profile; use a custom sequential/stateful checker",
                required=spec.action_behavior == "reject_infeasible",
            ),
        )
    findings = []
    seed = assignments_for(profile, spec)
    if spec.action_behavior == "reject_infeasible":
        try:
            # Config/fixture construction failures occur outside the expected rejection block.
            registry.validate_config(config)
            candidates = invalid_assignments(problem, seed)
            candidates.extend(
                case.assignments for case in spec.reference_cases if not case.feasible
            )
            for variable in problem.variables:
                if variable.shape == "vector":
                    original = seed[variable.name]
                    assert isinstance(original, tuple)
                    candidates.append({**seed, variable.name: original[:-1]})
            for assignment in candidates:
                actions = actions_for(profile, assignment, spec)
                try:
                    validate_profile(registry, config, state, actions)
                except ValueError:
                    continue
                raise ValueError("Validator accepted an action outside the declared domain")
            for case in spec.reference_cases:
                if case.feasible:
                    actions = actions_for(profile, case.assignments, spec)
                    validate_profile(registry, config, state, actions)
                    mechanism = registry.mechanisms[config.mechanism_id]()
                    verify_profile(
                        problem,
                        spec,
                        actions,
                        mechanism.evaluate(
                            config.world.model_copy(deep=True), state.model_copy(deep=True), actions
                        ),
                    )
            findings.append(
                VerificationFinding(
                    id="numeric_behavior",
                    status="verified" if candidates else "unverified",
                    evidence=f"Checked {len(candidates)} infeasible/shape mutations and declared feasible cases; finite tests, not exhaustive proof",
                )
            )
        except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
            findings.append(
                VerificationFinding(id="numeric_behavior", status="failed", evidence=str(exc))
            )
    else:
        findings.append(
            VerificationFinding(
                id="numeric_behavior",
                status="unverified",
                evidence="No generic reject rule assumed; use the declared custom checker or review this gap",
                required=False,
            )
        )
    for parameter_case in spec.parameter_cases:
        try:
            if set(parameter_case.parameters) - problem.parameters.keys():
                raise ValueError("Parameter case changes an unknown problem parameter")
            changed = ProblemStatement.model_validate(
                problem.model_copy(
                    update={"parameters": {**problem.parameters, **parameter_case.parameters}}
                ).model_dump()
            )
            data = config.model_dump(mode="json")
            data["world"]["parameters"].update(
                {
                    key: list(value) if isinstance(value, tuple) else value
                    for key, value in parameter_case.parameters.items()
                }
            )
            # These checks evaluate mechanisms/solvers directly, without calling actor policies.
            variant = SimulationConfig.from_json_values(data)
            mechanism = registry.mechanisms[config.mechanism_id]()
            mechanism.validate_config(variant.world.model_copy(deep=True))
            actions = actions_for(profile, parameter_case.assignments, spec)
            validate_profile(registry, variant, state, actions)
            verify_profile(
                changed,
                spec,
                actions,
                mechanism.evaluate(
                    variant.world.model_copy(deep=True), state.model_copy(deep=True), actions
                ),
            )
            if variant.benchmark is not None:
                benchmark = variant.benchmark
                view = registry.game_views[benchmark.game_view_id](
                    variant, state.model_copy(deep=True), mechanism
                )
                result = registry.solvers[benchmark.solver_id]().solve(
                    view, dict(benchmark.parameters)
                )
                if not result.equilibria:
                    raise ValueError("Parameter case produced no benchmark solution")
                for solution in result.equilibria:
                    assignment = verify_profile(changed, spec, solution.actions, solution.outcome)
                    if spec.independent_reference == "single_objective_slsqp":
                        from math import isclose

                        expected = independent_optimum(changed, assignment)
                        actual = changed.evaluate(assignment).objectives[changed.objectives[0].name]
                        if not isclose(
                            actual, expected, rel_tol=spec.tolerance, abs_tol=spec.tolerance
                        ):
                            raise ValueError(
                                "Parameter benchmark disagrees with independent reference"
                            )
            findings.append(
                VerificationFinding(
                    id="parameter:" + parameter_case.id,
                    status="verified",
                    evidence="Fresh mechanism/solver instances checked against the changed structured problem; no actor calls",
                )
            )
        except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
            findings.append(
                VerificationFinding(
                    id="parameter:" + parameter_case.id, status="failed", evidence=str(exc)
                )
            )
    return tuple(findings)


def verify_llm_observations(artifact: JobResult) -> VerificationFinding:
    """Verify trusted llm.v1 request identity and permissions against precommit states.

    Custom policies may define different request envelopes; this check does not
    pretend to validate those protocols. It is independent of economic mechanisms.
    """
    import json

    from simulation_core.observation import observe, permissions_for
    from simulation_core.types import Observation

    config = artifact.manifest.simulation
    actors = {actor.id: actor for actor in config.world.actors}
    checked = 0
    try:
        flattened = tuple(call for event in artifact.result.events for call in event.model_calls)
        if flattened != artifact.result.model_calls:
            raise ValueError("Run model calls differ from the canonical event records")
        for previous, event in zip(artifact.result.events, artifact.result.events[1:]):
            expected_actors = {
                d.action.actor_id
                for d in event.decisions
                if actors[d.action.actor_id].policy_id == "llm.v1"
            }
            accepted = []
            for call in event.model_calls:
                actor = actors[call.actor_id]
                if actor.policy_id != "llm.v1":
                    continue
                if actor.id not in expected_actors:
                    raise ValueError("Recorded call has no committed actor decision")
                if call.request.get("actor_id") != actor.id:
                    raise ValueError("Request identity differs from recorded actor")
                packet = json.loads(str(call.request["input_json"]))
                observation = Observation.from_json_values(packet["observation"])
                if observation.actor_id != actor.id:
                    raise ValueError("Observation identity differs from recorded actor")
                expected = observe(
                    actor, previous.state, permissions_for(config, actor.id, previous.state.phase)
                )
                if observation != expected:
                    raise ValueError("Observation differs from the authorized precommit snapshot")
                if call.status == "accepted":
                    accepted.append(actor.id)
                checked += 1
            if set(accepted) != expected_actors or len(accepted) != len(expected_actors):
                raise ValueError("Each llm.v1 decision requires exactly one accepted call")
    except (ValueError, TypeError, KeyError) as exc:
        return VerificationFinding(id="llm_observation_privacy", status="failed", evidence=str(exc))
    return VerificationFinding(
        id="llm_observation_privacy",
        status="verified" if checked else "unverified",
        evidence=f"Checked {checked} llm.v1 requests against canonical precommit observations, including identity, public/private facts and memory",
        required=bool(checked),
    )
