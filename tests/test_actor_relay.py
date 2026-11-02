"""Exercise the actual duplex transport without provider/network access."""

import json
import sys
from pathlib import Path

from agent_tools.actor_relay import PREFIX, ActorRelay
from agent_tools.process import bounded_command
from simulation_core.model_gateway import FakeGateway, ModelRequest


def test_worker_socket_subprocess_and_host_exchange():
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
    requests = []

    def exchange(line: str) -> str | None:
        if not line.startswith(PREFIX):
            return None
        requests.append(ModelRequest.model_validate_json(line[len(PREFIX) :]))
        return json.dumps({"response": {"text": "actual transport response", "model": "allowed"}})

    result = bounded_command(
        [sys.executable, "-c", script], seconds=15, max_bytes=100000, exchange=exchange
    )
    assert result.code == 0, result.stderr
    assert json.loads(result.stdout) == {"completed": True}
    assert len(requests) == 1


def test_host_relay_rejects_unauthorized_model_without_calling_provider(tmp_path: Path):
    # Construct only the authorization boundary; no generated code is imported.
    relay = object.__new__(ActorRelay)
    relay.gateway = FakeGateway(lambda request: "should not run")
    relay.model = "allowed"
    relay.actors = {"bidder"}
    relay.audit = tmp_path
    relay.calls = 0
    request = ModelRequest(
        actor_id="bidder",
        model="coding-model",
        instructions="",
        input_json="{}",
        response_schema={},
        max_output_tokens=100,
    )
    reply = json.loads(relay.exchange(PREFIX + request.model_dump_json()) or "{}")
    assert reply == {"error": "unauthorized_actor_or_model"}
    assert relay.gateway.requests == []
    assert (tmp_path / "actor-0001.json").stat().st_mode & 0o777 == 0o600
