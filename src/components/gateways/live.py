"""Host-side provider selection shared by example experiments; no model calls here."""

from simulation_core.model_gateway import ModelGateway

from .meta import MetaResponsesGateway
from .openai import OpenAIResponsesGateway
from .settings import LiveModelSettings


def configured_gateway(model: str | None = None) -> tuple[str, ModelGateway]:
    settings = LiveModelSettings.load(model)
    gateway_type = (
        MetaResponsesGateway if settings.model.startswith("muse-") else OpenAIResponsesGateway
    )
    return settings.model, gateway_type(
        settings.api_key.get_secret_value(), frozenset({settings.model})
    )
