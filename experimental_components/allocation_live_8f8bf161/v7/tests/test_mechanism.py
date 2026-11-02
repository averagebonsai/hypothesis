from experiment_extension.mechanism import AllocationMechanism
from experiment_extension.schemas import AllocationPayload
from pydantic import ValidationError

from simulation_core.types import Action, WorldConfig, WorldState


def _config(budget=10.0, target=(8.0, 6.0)):
    return WorldConfig.model_validate(
        {
            "actors": [
                {
                    "id": "allocator",
                    "kind": "allocator",
                    "action_space": {
                        "schemas": {
                            "allocate": "experimental.allocation_live_8f8bf161.action"
                        }
                    },
                    "policy_id": "scripted.v1",
                    "policy_parameters": {
                        "kind": "allocate",
                        "payload": {"allocation": [5.0, 5.0]},
                    },
                }
            ],
            "parameters": {"budget": budget, "target": list(target)},
            "initial_public_state": {"budget": budget, "target": list(target)},
        }
    )


def _state():
    return WorldState.model_validate(
        {
            "tick": 0,
            "phase": "act",
            "public": {"budget": 10.0, "target": [8.0, 6.0]},
            "private": {"allocator": {"facts": {}, "memory": {}}},
        }
    )


def test_action_schema_valid():
    p = AllocationPayload.model_validate({"allocation": [5.0, 5.0]})
    assert list(p.allocation) == [5.0, 5.0]


def test_mechanism_scores():
    mech = AllocationMechanism()
    outcome = mech.evaluate(
        _config(),
        _state(),
        [Action.model_validate({"actor_id": "allocator", "kind": "allocate", "payload": {"allocation": [5.0, 5.0]}})],
    )
    assert abs(outcome.payoffs["allocator"] - (-18.0)) < 1e-9


def test_mechanism_rejects():
    import pytest

    with pytest.raises(ValidationError):
        AllocationPayload.model_validate({"allocation": [float("nan")]})
    mech = AllocationMechanism()
    with pytest.raises(ValueError, match="dimension"):
        mech.validate_actions(
            _config(),
            _state(),
            [Action.model_validate({"actor_id": "allocator", "kind": "allocate", "payload": {"allocation": [5.0]}})],
        )
