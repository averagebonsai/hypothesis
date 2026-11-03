"""Exercise the actual duplex transport without provider/network access."""

import json
import sys
from pathlib import Path

import pytest

from agent_tools.actor_relay import PREFIX, ActorRelay
from agent_tools.process import bounded_command
from simulation_core.model_gateway import FakeGateway, ModelRequest


@pytest.mark.parametrize("redirect_before_relay", [True, False])
def test_worker_socket_subprocess_and_host_exchange(redirect_before_relay):
    script = '''
import contextlib
import subprocess
import sys
from extension_worker.actor_relay import serve
with serve(True), contextlib.redirect_stdout(sys.stderr):
    child = subprocess.run([sys.executable, "-c", """
from extension_worker.actor_relay import RelayGateway
from simulation_core.model_gateway import ModelRequest
r = ModelRequest(actor_id='bidder', model='allowed', instructions='choose',
    input_json='{}', response_schema={}, max_output_tokens=100)
assert RelayGateway().complete(r).text == 'actual transport response'
"""], check=True)
print('{"completed":true}')
'''
    if redirect_before_relay:
        script = script.replace(
            "with serve(True), contextlib.redirect_stdout(sys.stderr):",
            "with contextlib.redirect_stdout(sys.stderr), serve(True, output=sys.__stdout__):",
        )
    requests = []

    def exchange(line: str) -> str | None:
        if not line.startswith(PREFIX):
            return None
        envelope = json.loads(line[len(PREFIX) :])
        requests.append(ModelRequest.model_validate(envelope["request"]))
        return json.dumps(
            {
                "transport_id": envelope["transport_id"],
                "response": {"text": "actual transport response", "model": "allowed"},
            }
        )

    result = bounded_command(
        [sys.executable, "-c", script], seconds=15, max_bytes=100000, exchange=exchange
    )
    assert result.code == 0, result.stderr
    assert json.loads(result.stdout) == {"completed": True}
    assert len(requests) == 1


def test_host_relay_rejects_unauthorized_model_without_calling_provider(tmp_path: Path, artifact):
    # Construct only the authorization boundary; no generated code is imported.
    provider = FakeGateway(lambda request: "should not run")
    relay = ActorRelay(provider, "allowed", artifact.manifest, tmp_path)
    request = ModelRequest(
        actor_id=artifact.manifest.simulation.world.actors[0].id,
        model="coding-model",
        instructions="",
        input_json="{}",
        response_schema={},
        max_output_tokens=100,
    )
    reply = json.loads(relay.exchange(PREFIX + request.model_dump_json()) or "{}")
    assert reply["error"] == "unauthorized_actor_or_model"
    assert reply["error_metadata"]["output_tokens"] == 0
    assert provider.requests == []
    assert (tmp_path / "actor-0001.json").stat().st_mode & 0o777 == 0o600


def test_local_relay_has_no_shorter_generation_deadline(monkeypatch):
    from extension_worker import actor_relay

    timeouts = []

    class Stream:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def write(self, text):
            pass

        def flush(self):
            pass

        def readline(self, limit):
            return '{"response":{"text":"slow valid decision","model":"allowed"}}\n'

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def settimeout(self, value):
            timeouts.append(value)

        def connect(self, path):
            pass

        def makefile(self, mode):
            return Stream()

    monkeypatch.setenv(actor_relay.ENV, "/fake/current-trial.sock")
    monkeypatch.setattr(actor_relay.socket, "socket", lambda *args, **kwargs: Connection())
    r = actor_relay.RelayGateway().complete(
        ModelRequest(
            actor_id="p1",
            model="allowed",
            instructions="Rules",
            input_json="{}",
            response_schema={},
        )
    )
    assert r.text == "slow valid decision" and timeouts == [None]


def test_concurrent_socket_requests_match_out_of_order_host_replies():
    import time
    from threading import Barrier

    barrier = Barrier(3, timeout=5)
    completed = []
    script = """
import contextlib, sys
from concurrent.futures import ThreadPoolExecutor
from extension_worker.actor_relay import serve, RelayGateway
from simulation_core.model_gateway import ModelRequest
def call(actor):
    r = ModelRequest(actor_id=actor, model="fake", instructions="rules", input_json="{}", response_schema={})
    assert RelayGateway().complete(r).text == actor
with serve(True), contextlib.redirect_stdout(sys.stderr):
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(call, ["a", "b", "c"]))
print('{"completed":true}')
"""

    def exchange(line):
        if not line.startswith(PREFIX):
            return None
        envelope = json.loads(line[len(PREFIX) :])
        actor = envelope["request"]["actor_id"]
        barrier.wait()  # Both the worker relay and host pump must allow overlap.
        time.sleep({"a": 0.2, "b": 0.1, "c": 0}[actor])
        completed.append(actor)
        return json.dumps(
            {"transport_id": envelope["transport_id"], "response": {"text": actor, "model": "fake"}}
        )

    result = bounded_command(
        [sys.executable, "-c", script],
        seconds=15,
        max_bytes=100000,
        exchange=exchange,
        exchange_workers=3,
    )
    assert result.code == 0, result.stderr
    assert json.loads(result.stdout) == {"completed": True}
    assert completed == ["c", "b", "a"]


def test_malformed_host_request_is_rejected_without_provider_call(tmp_path, artifact):
    provider = FakeGateway(lambda request: pytest.fail("Must not call provider"))
    relay = ActorRelay(provider, "fake", artifact.manifest, tmp_path)
    reply = json.loads(relay.exchange(PREFIX + "[]"))
    assert reply["error"] == "invalid_actor_request"
