"""Meta's documented Responses-compatible endpoint, with the same gateway contract."""

from .openai import OpenAIResponsesGateway


class MetaResponsesGateway(OpenAIResponsesGateway):
    endpoint = "https://api.meta.ai/v1/responses"
