"""Reference interface contract for a composable simulation engine.

This is intentionally a SINGLE review artifact. Split it at the FILE BOUNDARY
markers into the suggested modules before implementing. The contracts are
Python 3.12+ and use Pydantic v2. Concrete implementations are out of scope.

Architecture: Actor + Policy + World + Mechanism + Protocol + Experiment,
optional Solver, and trusted Runtime. No generated code should execute in the
host controller's process.
"""

# ============================================================================
# FILE: simulation_core/types.py
# Put shared IDs, schemas, immutable values, and result DTOs in ONE file.
# ============================================================================
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Mapping, Protocol as TypingProtocol, Sequence, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

ActorId: TypeAlias = str
JSONValue: TypeAlias = Any  # Boundary: serialized JSON-compatible values only.


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ActionSpace(FrozenModel):
    """Allowed actions FOR THIS SIMULATION, not universal actor capabilities.

    `schemas` maps action kind to a registered, versioned Pydantic schema ID.
    Dynamic phase-specific action permissions are deliberately out of v1 scope.
    """
    schemas: dict[str, str] = Field(min_length=1)


class Actor(FrozenModel):
    id: ActorId
    kind: str
    attributes: dict[str, JSONValue] = Field(default_factory=dict)
    action_space: ActionSpace
    policy_id: str


class Action(FrozenModel):
    actor_id: ActorId
    kind: str
    payload: dict[str, JSONValue] = Field(default_factory=dict)


class Observation(FrozenModel):
    actor_id: ActorId
    phase: str
    visible: dict[str, JSONValue]
    memory: dict[str, JSONValue] = Field(default_factory=dict)
    allowed_action_kinds: tuple[str, ...]


class WorldConfig(FrozenModel):
    """Exogenous initial conditions; immutable for a particular run."""
    actors: tuple[Actor, ...]
    parameters: dict[str, JSONValue] = Field(default_factory=dict)
    initial_public_state: dict[str, JSONValue] = Field(default_factory=dict)
    initial_private_state: dict[ActorId, dict[str, JSONValue]] = Field(default_factory=dict)
    initial_memory: dict[ActorId, dict[str, JSONValue]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique_actors(self) -> WorldConfig:
        ids = [a.id for a in self.actors]
        if len(ids) != len(set(ids)):
            raise ValueError("Actor IDs must be unique")
        return self


class WorldState(FrozenModel):
    """Authoritative evolving state; NEVER passed directly to an LLM policy."""
    tick: int = Field(ge=0)
    phase: str
    public: dict[str, JSONValue] = Field(default_factory=dict)
    private: dict[ActorId, dict[str, JSONValue]] = Field(default_factory=dict)
    memory: dict[ActorId, dict[str, JSONValue]] = Field(default_factory=dict)
    pending_actions: dict[ActorId, Action] = Field(default_factory=dict)


class Outcome(FrozenModel):
    """Pure hypothetical evaluation; no committed state change."""
    payoffs: dict[ActorId, float] = Field(default_factory=dict)
    metrics: dict[str, JSONValue] = Field(default_factory=dict)


class TransitionResult(FrozenModel):
    next_state: WorldState
    outcome: Outcome
    events: tuple[dict[str, JSONValue], ...] = ()


class SolveResult(FrozenModel):
    actions: tuple[Action, ...]
    converged: bool
    diagnostics: dict[str, JSONValue] = Field(default_factory=dict)


class RunResult(FrozenModel):
    final_state: WorldState
    outcomes: tuple[Outcome, ...]
    events: tuple[dict[str, JSONValue], ...]
    diagnostics: dict[str, JSONValue] = Field(default_factory=dict)


# ============================================================================
# FILE: simulation_core/policy.py
# Policy and its restricted decision/evaluation context stay together.
# ============================================================================
class DecisionContext(TypingProtocol):
    """Narrow capability object. Do not expose unrestricted WorldState.

    A solver/optimization policy may query an AUTHORIZED payoff oracle. This
    contract is scoped to information legally available to the actor.
    """
    def evaluate_candidate(self, action: Action) -> Outcome: ...


class Policy(ABC):
    """Chooses actions; never mutates authoritative world state."""
    @abstractmethod
    def required_observation_fields(self) -> frozenset[str]: ...

    @abstractmethod
    def choose_action(
        self, observation: Observation, context: DecisionContext
    ) -> Action: ...


# ============================================================================
# FILE: simulation_core/mechanism.py
# The base mechanism stays here; concrete demand/cost/payoff models go in
# components/mechanisms/*.py and can be composed inside one mechanism.
# ============================================================================
class Mechanism(ABC):
    """Defines consequences of actions, not action choice or turn order.

    evaluate is pure and must not consume mutable global RNG state. For
    stochastic mechanisms, pass keyed draws/scenarios via explicit inputs in
    a concrete versioned contract before implementing stochastic solvers.
    """
    @abstractmethod
    def evaluate(
        self, config: WorldConfig, state: WorldState,
        actions: Sequence[Action]
    ) -> Outcome: ...

    @abstractmethod
    def transition(
        self, config: WorldConfig, state: WorldState,
        actions: Sequence[Action]
    ) -> TransitionResult: ...


# ============================================================================
# FILE: simulation_core/protocol.py
# Scheduling and observation permissions belong together, not in Policy.
# ============================================================================
class Protocol(ABC):
    """Owns timing, visibility rules, action batching and termination."""
    @abstractmethod
    def active_actor_ids(self, config: WorldConfig, state: WorldState) -> tuple[ActorId, ...]: ...

    @abstractmethod
    def observe(
        self, config: WorldConfig, state: WorldState, actor_id: ActorId
    ) -> Observation: ...

    @abstractmethod
    def is_terminal(self, config: WorldConfig, state: WorldState) -> bool: ...

    @abstractmethod
    def validate_action_batch(
        self, config: WorldConfig, state: WorldState,
        actions: Sequence[Action]
    ) -> None: ...


# ============================================================================
# FILE: simulation_core/solver.py
# Solver + read-only GameView live together. Solver is OPTIONAL.
# ============================================================================
class GameView(TypingProtocol):
    """Read-only, authorized game representation for equilibrium algorithms.

    For complete-information Nash games, payoff queries may cover joint
    action profiles. For private-information games, use a specialized view
    exposing beliefs/type distributions instead of leaking hidden state.
    """
    def actor_ids(self) -> tuple[ActorId, ...]: ...
    def action_space(self, actor_id: ActorId) -> ActionSpace: ...
    def evaluate_profile(self, actions: Sequence[Action]) -> Outcome: ...


class Solver(ABC):
    @abstractmethod
    def solve(self, game: GameView) -> SolveResult: ...


# ============================================================================
# FILE: simulation_core/experiment.py
# Experimental design is distinct from a single SimulationConfig/run.
# ============================================================================
class ExecutionMode(str, Enum):
    POLICY_DRIVEN = "policy_driven"
    SOLVER_DRIVEN = "solver_driven"


class SimulationConfig(FrozenModel):
    world: WorldConfig
    mechanism_id: str
    protocol_id: str
    execution_mode: ExecutionMode
    solver_id: str | None = None
    seed: int = 0
    max_steps: int = Field(default=100, gt=0)

    @model_validator(mode="after")
    def solver_required(self) -> SimulationConfig:
        if self.execution_mode == ExecutionMode.SOLVER_DRIVEN and not self.solver_id:
            raise ValueError("solver_id required for solver_driven mode")
        if self.execution_mode == ExecutionMode.POLICY_DRIVEN and self.solver_id:
            raise ValueError("solver_id must be omitted for policy_driven mode")
        return self


class Treatment(FrozenModel):
    id: str
    # Declarative, validated overrides; no arbitrary Python expressions.
    overrides: dict[str, JSONValue] = Field(default_factory=dict)


class ExperimentConfig(FrozenModel):
    hypothesis: str
    base_simulation: SimulationConfig
    treatments: tuple[Treatment, ...] = ()
    outcome_metric_ids: tuple[str, ...] = ()
    repetitions: int = Field(default=1, ge=1)
    seed: int = 0


class ExperimentEvaluator(ABC):
    @abstractmethod
    def summarize(self, runs: Mapping[str, Sequence[RunResult]]) -> dict[str, JSONValue]: ...


# ============================================================================
# FILE: simulation_core/runtime.py
# The trusted runtime owns the loop, state commits, validation and event log.
# ============================================================================
class SimulationRuntime(ABC):
    """Implement once. Do not let generated plugins override this contract."""
    @abstractmethod
    def run(self, config: SimulationConfig) -> RunResult: ...


# ============================================================================
# FILE: simulation_core/registry.py
# Registry resolves versioned component IDs to approved implementations.
# ============================================================================
class ComponentRegistry(ABC):
    @abstractmethod
    def policy(self, policy_id: str) -> Policy: ...

    @abstractmethod
    def mechanism(self, mechanism_id: str) -> Mechanism: ...

    @abstractmethod
    def protocol(self, protocol_id: str) -> Protocol: ...

    @abstractmethod
    def solver(self, solver_id: str) -> Solver: ...

    @abstractmethod
    def action_schema(self, schema_id: str) -> type[BaseModel]: ...


# ============================================================================
# FILE: simulation_core/execution.py
# ExecutionBackend is deployment infrastructure, NOT an economic primitive.
# ============================================================================
class ExecutionBackend(ABC):
    @abstractmethod
    def execute(self, config: SimulationConfig) -> RunResult: ...


class ExperimentRunner(ABC):
    """Orchestrates baseline/treatments/repetitions using ExecutionBackend."""
    @abstractmethod
    def run_experiment(
        self, experiment: ExperimentConfig
    ) -> Mapping[str, Sequence[RunResult]]: ...


# IMPLEMENTATION NOTES (not code):
# 1. All data exchanged with worker processes must be JSON-serializable.
# 2. Define concrete discriminated Action payload schemas in separate files.
# 3. The runtime validates schema + actor ownership + protocol legality before
#    any transition; it validates resulting state invariants before committing.
# 4. For simultaneous games, keep pending actions hidden until batch commit.
# 5. An equilibrium solver's payoff oracle must be pure; failure to converge is
#    a reported outcome, not permission to silently commit a candidate.
# 6. WorldConfig is exogenous and immutable; WorldState owns changing memory.
# 7. Generated extensions run in isolated workers, not in the host controller.
# 8. For a Stackelberg solver, backward induction uses hypothetical follower
#    responses; do not confuse it with a two-turn behavioral trajectory.