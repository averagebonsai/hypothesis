"""Credential-free Unix socket relay shared by worker and acceptance subprocesses.

Only the host performs provider calls. The worker retains network=none; this
socket lives in its disposable /tmp and carries bounded DTOs, never credentials.
"""

import json
import os
import select
import socket
import sys
import tempfile
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from queue import Queue
from typing import Literal, TextIO
from uuid import uuid4

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
            # The provider and outer worker own deadlines. A shorter local socket
            # timeout can discard a valid slow response while the host is still
            # generating it, losing an otherwise completed actor decision.
            connection.settimeout(None)
            connection.connect(os.environ[ENV])
            with connection.makefile("rw") as stream:
                payload = request.model_dump_json()
                if len(payload) > MAX_FRAME - 1:
                    raise GatewayError("request_too_large")
                stream.write(payload + "\n")
                stream.flush()
                value = json.loads(read_line(stream))
                if "error" in value:
                    raise GatewayError(value["error"], **value.get("error_metadata", {}))
                return ModelResponse.model_validate(value["response"])


@contextmanager
def serve(enabled: bool, *, output: TextIO | None = None) -> Iterator[None]:
    """Bridge local subprocesses to original stdio, before stdout is redirected."""
    if not enabled:
        yield
        return
    output, input_stream = output or sys.stdout, sys.stdin
    with tempfile.TemporaryDirectory(prefix="actor-relay-") as directory:
        path = str(Path(directory) / "gateway.sock")
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(path)
        server.listen(8)
        server.settimeout(0.2)
        os.environ[ENV] = path
        stopped = threading.Event()

        pending: dict[str, Queue[str]] = {}
        lock = threading.Lock()
        output_lock = threading.Lock()
        clients = ThreadPoolExecutor(max_workers=32)

        def dispatch() -> None:
            # One reader, correlated replies; completion order may differ from arrival order.
            buffer = b""
            try:
                while not stopped.is_set():
                    if not select.select([input_stream], [], [], 0.2)[0]:
                        continue
                    chunk = os.read(input_stream.fileno(), MAX_FRAME)
                    if not chunk:
                        raise GatewayError("actor_relay_closed")
                    buffer += chunk
                    while b"\n" in buffer:
                        reply, buffer = buffer.split(b"\n", 1)
                        if len(reply) > MAX_FRAME:
                            raise GatewayError("invalid_relay_frame")
                        value = json.loads(reply)
                        if not isinstance(value, dict):
                            raise GatewayError("invalid_relay_frame")
                        key = value.pop("transport_id")
                        if not isinstance(key, str):
                            raise GatewayError("invalid_relay_frame")
                        with lock:
                            target = pending.get(key)
                        if target is not None:
                            target.put(json.dumps(value) + "\n")
                    if len(buffer) > MAX_FRAME:
                        raise GatewayError("invalid_relay_frame")
            except (OSError, ValueError, KeyError, GatewayError):
                with lock:
                    for target in pending.values():
                        target.put('{"error":"actor_relay_failed"}\n')

        def handle(connection: socket.socket) -> None:
            key = uuid4().hex
            target: Queue[str] = Queue()
            with lock:
                pending[key] = target
            try:
                with connection, connection.makefile("rw") as stream:
                    request = ModelRequest.model_validate_json(read_line(stream))
                    with output_lock:
                        output.write(
                            PREFIX
                            + json.dumps(
                                {"transport_id": key, "request": request.model_dump(mode="json")}
                            )
                            + "\n"
                        )
                        output.flush()
                    stream.write(target.get())
                    stream.flush()
            except (OSError, ValueError, GatewayError):
                pass
            finally:
                with lock:
                    pending.pop(key, None)

        def run() -> None:
            while not stopped.is_set():
                try:
                    connection, _ = server.accept()
                except TimeoutError:
                    continue
                except OSError:
                    break
                clients.submit(handle, connection)

        reader = threading.Thread(target=dispatch, daemon=True)
        reader.start()
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        try:
            yield
        finally:
            stopped.set()
            server.close()
            with lock:
                for target in pending.values():
                    target.put('{"error":"actor_relay_closed"}\n')
            clients.shutdown(wait=True, cancel_futures=True)
            thread.join(timeout=1)
            reader.join(timeout=1)
            os.environ.pop(ENV, None)
