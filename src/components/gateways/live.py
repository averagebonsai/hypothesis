"""Host-side provider selection shared by example experiments; no model calls here."""

from pathlib import Path

from simulation_core.model_gateway import ModelGateway

from .meta import MetaResponsesGateway
from .openai import OpenAIResponsesGateway
from .pool import GatewayPool
from .settings import LiveModelSettings


def configured_gateway(
    model: str | None = None,
    *,
    timeout: float = 180,
    stream: bool = True,
) -> tuple[str, ModelGateway]:
    settings = LiveModelSettings.load(model)
    keys = settings.actor_api_keys or (settings.api_key,)
    gateways = tuple(
        _gateway(
            settings.model_copy(update={"api_key": key}),
            timeout=timeout,
            stream=stream,
        )[1]
        for key in keys
    )
    return settings.model, GatewayPool(gateways, settings.model)


def configured_coding_gateway(env_file: Path | None = None) -> tuple[str, ModelGateway]:
    """Coding credentials/model are selected independently of simulation actors."""
    return _gateway(
        LiveModelSettings.load(role="coding", env_file=env_file),
        timeout=900,
        max_response_bytes=800000,
        stream=True,
    )


def _gateway(
    settings: LiveModelSettings,
    *,
    timeout: float = 45,
    max_response_bytes: int = 200000,
    stream: bool = False,
) -> tuple[str, ModelGateway]:
    gateway_type = (
        MetaResponsesGateway if settings.model.startswith("muse-") else OpenAIResponsesGateway
    )
    return settings.model, gateway_type(
        settings.api_key.get_secret_value(),
        frozenset({settings.model}),
        timeout=timeout,
        max_response_bytes=max_response_bytes,
        stream=stream,
    )
