"""Offline tests; credentials below are synthetic and never sent to a provider."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from agent_tools.execution_settings import ActorExecutionSettings
from components.gateways.pool import GatewayPool
from components.gateways.settings import LiveModelSettings
from simulation_core.model_gateway import FakeGateway, GatewayError, ModelRequest


def test_numbered_actor_keys_are_unique_host_only_and_coding_uses_primary(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text(
        "API_KEY=synthetic-primary\nAPI_KEY_2=synthetic-second\nAPI_KEY_3=synthetic-second\nAPI_KEY_10=synthetic-tenth\nMODEL=actor\nMODEL_CODING=muse-spark-1.3\n"
    )
    for name in (
        "API_KEY",
        "API_KEY_2",
        "API_KEY_3",
        "API_KEY_10",
        "OPENAI_API_KEY",
        "MODEL",
        "MODEL_CODING",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = LiveModelSettings.load(env_file=path)
    assert len(settings.actor_api_keys) == 3
    assert "synthetic" not in settings.model_dump_json()
    assert settings.model_dump() == {"model": "actor"}
    coding = LiveModelSettings.load(env_file=path, role="coding")
    assert coding.actor_api_keys == ()
    assert coding.api_key.get_secret_value() == "synthetic-primary"


def test_credential_slots_overlap_and_return_to_pool_after_failure():
    barrier = Barrier(3, timeout=3)
    seen = []

    def respond(request):
        barrier.wait()
        return request.actor_id

    pool = GatewayPool(tuple(FakeGateway(respond) for _ in range(3)), "fake")

    def call(index):
        request = ModelRequest(
            actor_id=str(index),
            model="fake",
            instructions="rules",
            input_json="{}",
            response_schema={},
        )
        response = pool.complete(request)
        seen.append(pool.route_metadata)
        return response.text

    with ThreadPoolExecutor(max_workers=3) as executor:
        assert list(executor.map(call, range(3))) == ["0", "1", "2"]
    assert {item["credential_slot"] for item in seen} == {1, 2, 3}
    assert all(item["credential_wait_seconds"] >= 0 for item in seen)

    def fail(request):
        raise GatewayError("synthetic_error")

    failed = GatewayPool((FakeGateway(fail),), "fake")
    import pytest

    for _ in range(2):
        with pytest.raises(GatewayError):
            failed.complete(
                ModelRequest(
                    actor_id="a", model="fake", instructions="", input_json="{}", response_schema={}
                )
            )


def test_fast_default_budgets_follow_schedule_instead_of_fixed_48():
    from examples.measurements import run_job

    config = run_job().manifest.simulation
    from simulation_core.types import Actor

    actors = tuple(
        Actor.model_validate(
            {
                **actor.model_dump(),
                "policy_id": "llm.v1",
                "policy_parameters": {"model": "fake", "instructions": "choose"},
            }
        )
        for actor in config.world.actors
    )
    config = config.model_copy(
        update={
            "world": config.world.model_copy(update={"actors": actors}),
            "protocol_id": "simultaneous.v1",
            "protocol_parameters": {"rounds": 100},
            "max_steps": 100,
        }
    )
    settings = ActorExecutionSettings(model="fake")
    settings.validate_budget(config)
    resolved = settings.resolve(config)
    assert all(actor.policy_parameters["max_calls"] == 200 for actor in resolved.world.actors)
    assert settings.call_budgets(config)[0] == 200 * len(actors)


@pytest.mark.parametrize("count", [1, 4, 12])
def test_actor_key_discovery_has_no_fixed_key_count(tmp_path, monkeypatch, count):
    import os
    import re

    for name in tuple(os.environ):
        if name in {"API_KEY", "OPENAI_API_KEY", "MODEL"} or re.fullmatch(r"API_KEY_[0-9]+", name):
            monkeypatch.delenv(name, raising=False)
    path = tmp_path / ".env"
    entries = ["API_KEY=synthetic-1", "MODEL=synthetic-model"]
    entries += [f"API_KEY_{index}=synthetic-{index}" for index in range(2, count + 1)]
    path.write_text("\n".join(entries) + "\n")
    settings = LiveModelSettings.load(env_file=path)
    assert len(settings.actor_api_keys) == count
    assert [key.get_secret_value() for key in settings.actor_api_keys] == [
        f"synthetic-{index}" for index in range(1, count + 1)
    ]
    assert settings.model_dump() == {"model": "synthetic-model"}
