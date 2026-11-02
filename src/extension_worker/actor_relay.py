"""Credential-free Unix socket relay shared by worker and acceptance subprocesses.

Only the host performs provider calls. The worker retains network=none; this
socket lives in its disposable /tmp and carries bounded DTOs, never credentials.
"""

import json
import os
import socket
import sys
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal, TextIO

from simulation_core.model_gateway import GatewayError, ModelGateway, ModelRequest, ModelResponse

ENV = "HYPOTHESIS_ACTOR_RELAY"
PREFIX = "HYPOTHESIS_MODEL_REQUEST:"
MAX_FRAME = 200_000


def read_line(stream: TextIO) -> str:
    line = stream.readline(MAX_FRAME + 1)
    if not line or len(line) > MAX_FRAME or not line.endswith("\n"):
        raise GatewayError("invalid_relay_frame")
    return line


class RelayGateway(ModelGateway):
    @property
    def mode(self) -> Literal["live"]:
        return "live"

    def complete(self, request: ModelRequest) -> ModelResponse:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(75)
            connection.connect(os.environ[ENV])
            with connection.makefile("rw") as stream:
                payload = request.model_dump_json()
                if len(payload) > MAX_FRAME - 1:
                    raise GatewayError("request_too_large")
                stream.write(payload + "\n")
                stream.flush()
                value = json.loads(read_line(stream))
                if "error" in value:
                    raise GatewayError(value["error"])
                return ModelResponse.model_validate(value["response"])


@contextmanager
def serve(enabled: bool) -> Iterator[None]:
    """Bridge local subprocesses to original stdio, before stdout is redirected."""
    if not enabled:
        yield
        return
    output, input_stream = sys.stdout, sys.stdin
    with tempfile.TemporaryDirectory(prefix="actor-relay-") as directory:
        path = str(Path(directory) / "gateway.sock")
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(path)
        server.listen(8)
        server.settimeout(0.2)
        os.environ[ENV] = path
        stopped = threading.Event()

        def run() -> None:
            while not stopped.is_set():
                try:
                    connection, _ = server.accept()
                except TimeoutError:
                    continue
                except OSError:
                    break
                with connection, connection.makefile("rw") as stream:
                    try:
                        request = ModelRequest.model_validate_json(read_line(stream))
                        output.write(PREFIX + request.model_dump_json() + "\n")
                        output.flush()
                        reply = read_line(input_stream)
                    except Exception:  # noqa: BLE001 - sanitized relay boundary
                        reply = '{"error":"actor_relay_failed"}\n'
                    stream.write(reply)
                    stream.flush()

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        try:
            yield
        finally:
            stopped.set()
            server.close()
            thread.join(timeout=1)
            os.environ.pop(ENV, None)
