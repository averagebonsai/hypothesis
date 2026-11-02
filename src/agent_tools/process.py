"""Bounded subprocess transport for trusted CLI binaries, never shell strings."""

import os
import selectors
import subprocess
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessResult:
    code: int
    stdout: str
    stderr: str


class ProcessLimitError(RuntimeError):
    pass


def bounded_command(args: list[str], *, seconds: int, max_bytes: int) -> ProcessResult:
    process = subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL
    )
    selector = selectors.DefaultSelector()
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + seconds
    total = 0
    try:
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
                buffers[key.data].extend(data)
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
        for pipe in (process.stdout, process.stderr):
            if pipe:
                pipe.close()
