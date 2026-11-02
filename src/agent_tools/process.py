"""Bounded subprocess transport for trusted CLI binaries, never shell strings."""

import os
import selectors
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessResult:
    code: int
    stdout: str
    stderr: str


class ProcessLimitError(RuntimeError):
    pass


def bounded_command(
    args: list[str],
    *,
    seconds: int,
    max_bytes: int,
    exchange: Callable[[str], str | None] | None = None,
    input_text: str | None = None,
) -> ProcessResult:
    process = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.PIPE if exchange or input_text is not None else subprocess.DEVNULL,
    )
    selector = selectors.DefaultSelector()
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + seconds
    total = 0
    pending = bytearray()
    try:
        if input_text is not None:
            assert process.stdin is not None
            process.stdin.write(input_text.encode())
            process.stdin.close()
        for name, pipe in (("stdout", process.stdout), ("stderr", process.stderr)):
            if pipe is None:
                raise RuntimeError("Missing subprocess pipe")
            selector.register(pipe, selectors.EVENT_READ, name)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProcessLimitError("Worker command exceeded its wall-clock budget")
            for key, _ in selector.select(min(remaining, 0.2)):
                data = os.read(key.fd, 65536)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                total += len(data)
                if total > max_bytes:
                    raise ProcessLimitError("Worker command exceeded its output budget")
                if key.data == "stdout" and exchange is not None:
                    pending.extend(data)
                    while b"\n" in pending:
                        line, _, rest = pending.partition(b"\n")
                        pending = bytearray(rest)
                        reply = exchange(line.decode("utf-8"))
                        if reply is None:
                            buffers["stdout"].extend(line + b"\n")
                        else:
                            assert process.stdin is not None
                            process.stdin.write((reply + "\n").encode())
                            process.stdin.flush()
                else:
                    buffers[key.data].extend(data)
        buffers["stdout"].extend(pending)
        code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
        return ProcessResult(
            code,
            *(buffers[name].decode("utf-8", errors="replace") for name in ("stdout", "stderr")),
        )
    finally:
        selector.close()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        for pipe in (process.stdout, process.stderr, process.stdin):
            if pipe:
                pipe.close()
