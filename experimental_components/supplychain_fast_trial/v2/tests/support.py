"""Shared offline fixtures: scripted/sequenced policies and config builders.

All domain constants come from experiment_extension.configuration, the single
source of truth also used for the candidate, so the sealed bundle never reads
external files at test runtime.
"""

import json
from collections.abc import Sequence

from experiment_extension.configuration import (
    ASSUMPTIONS,
    INITIAL_PUBLIC_STATE,
    LOGISTICS_FACTS,
    MANUFACTURER_FACTS,
    PERMISSIONS,
    SUPPLIER_FACTS,
    WORLD_PARAMETERS,
)
from experiment_extension.supplychain import (
    LOGISTICS,
    MANUFACTURER,
    SUPPLIER_A,
    SUPPLIER_B,
    LogisticsAllocation,
    MakeAction,
    OrderAction,
    SupplierOffer,
    SupplyChainMechanism,
    schedule_phases,
)

from components.library import standard_registry
from simulation_core.execution import JobResult, JobRunner, LocalBackend
from simulation_core.policy import Policy
from simulation_core.registry import ComponentRegistry
from simulation_core.request import ExperimentRequest
from simulation_core.types import Action, Decision, Observation, SimulationConfig

PARAMS = WORLD_PARAMETERS
INITIAL_PUBLIC = INITIAL_PUBLIC_STATE


class SequencePolicy(Policy):
    """Deterministic offline stand-in: replays a queued action per call."""

    def __init__(self, actions: Sequence[tuple[str, dict]]) -> None:
        self._actions = list(actions)

    def required_observation_fields(self) -> frozenset[str]:
        return frozenset()

    def choose_action(self, observation: Observation) -> Decision:
        kind, payload = self._actions.pop(0)
        return Decision(
            action=Action(actor_id=observation.actor_id, kind=kind, payload=dict(payload)),
            rationale="Sequenced offline stand-in for a fixed action script.",
        )


def make_registry() -> ComponentRegistry:
    registry = standard_registry()
    registry.mechanisms["test.supplychain.v1"] = SupplyChainMechanism
    registry.action_schemas["test.order.v1"] = OrderAction
    registry.action_schemas["test.offer.v1"] = SupplierOffer
    registry.action_schemas["test.allocate.v1"] = LogisticsAllocation
    registry.action_schemas["test.make.v1"] = MakeAction
    return registry


def actor_entry(
    actor_id: str, kinds: dict[str, str], policy_id: str, policy_parameters: dict
) -> dict:
    return {
        "id": actor_id,
        "kind": "organization",
        "attributes": {},
        "action_space": {"schemas": kinds},
        "policy_id": policy_id,
        "policy_parameters": policy_parameters,
    }


def base_config(policy_map: dict[str, tuple[str, dict]]) -> SimulationConfig:
    """Full 36-phase config with a chosen policy per actor."""
    entries = {
        MANUFACTURER: {"order": "test.order.v1", "produce": "test.make.v1"},
        SUPPLIER_A: {"offer": "test.offer.v1"},
        SUPPLIER_B: {"offer": "test.offer.v1"},
        LOGISTICS: {"allocate": "test.allocate.v1"},
    }
    actors = [
        actor_entry(aid, kinds, policy_map[aid][0], policy_map[aid][1])
        for aid, kinds in entries.items()
    ]
    return SimulationConfig.from_json_values(
        json.loads(
            json.dumps(
                {
                    "world": {
                        "actors": actors,
                        "parameters": PARAMS,
                        "initial_public_state": INITIAL_PUBLIC,
                        "initial_private_state": {
                            "manufacturer": {"facts": MANUFACTURER_FACTS, "memory": {}},
                            "supplier_a": {"facts": SUPPLIER_FACTS, "memory": {}},
                            "supplier_b": {"facts": SUPPLIER_FACTS, "memory": {}},
                            "logistics": {"facts": LOGISTICS_FACTS, "memory": {}},
                        },
                    },
                    "mechanism_id": "test.supplychain.v1",
                    "protocol_id": "sequential.v1",
                    "protocol_parameters": {"phases": schedule_phases(9)},
                    "permissions": PERMISSIONS,
                    "max_steps": 36,
                    "assumptions": ASSUMPTIONS,
                }
            )
        )
    )


def scripted_config() -> SimulationConfig:
    """Full 36-phase config with zero-action scripted policies."""
    return base_config(
        {
            MANUFACTURER: (
                "scripted.v1",
                {"kind": "order", "payload": {"order_a": 0, "order_b": 0, "priority": "none"}},
            ),
            SUPPLIER_A: (
                "scripted.v1",
                {"kind": "offer", "payload": {"produce": 0, "offer": 0, "priority_request": False}},
            ),
            SUPPLIER_B: (
                "scripted.v1",
                {"kind": "offer", "payload": {"produce": 0, "offer": 0, "priority_request": False}},
            ),
            LOGISTICS: (
                "scripted.v1",
                {"kind": "allocate", "payload": {"alloc_a": 0, "alloc_b": 0}},
            ),
        }
    )


def run_with_sequences(script: dict[str, list[tuple[str, dict]]]) -> JobResult:
    """Run the full horizon with per-actor sequenced offline policies."""
    config = base_config({aid: (f"seq.{aid}", {}) for aid in script})
    registry = make_registry()
    for actor_id, actions in script.items():
        policy = SequencePolicy(list(actions))
        registry.policies[f"seq.{actor_id}"] = lambda _params, _p=policy: _p
    runner = JobRunner(LocalBackend(registry))
    return runner.run(ExperimentRequest(hypothesis="offline sequenced run"), config)
