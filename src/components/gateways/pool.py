"""Host-only credential leasing: one concurrent request per configured key."""

import time
from queue import Queue
from threading import local
from typing import Literal

from simulation_core.model_gateway import ModelGateway, ModelRequest, ModelResponse


class GatewayPool(ModelGateway):
    def __init__(self, gateways: tuple[ModelGateway, ...], model: str) -> None:
        if not gateways:
            raise ValueError("At least one actor credential is required")
        self.allowed_models = frozenset({model})
        self.size = len(gateways)
        self._mode = gateways[0].mode
        if any(gateway.mode != self._mode for gateway in gateways):
            raise ValueError("Credential pool must use a consistent gateway mode")
        self._available: Queue[tuple[int, ModelGateway]] = Queue()
        self._local = local()
        for slot, gateway in enumerate(gateways, 1):
            self._available.put((slot, gateway))

    @property
    def mode(self) -> Literal["fake", "live"]:
        return self._mode

    @property
    def route_metadata(self) -> dict[str, int | float]:
        return getattr(self._local, "route", {})

    def complete(self, request: ModelRequest) -> ModelResponse:
        started = time.monotonic()
        self._local.route = {}
        slot, gateway = self._available.get()
        self._local.route = {
            "credential_slot": slot,
            "credential_wait_seconds": time.monotonic() - started,
        }
        try:
            return gateway.complete(request)
        finally:
            self._available.put((slot, gateway))
