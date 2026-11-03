"""Explicit capabilities for policies using the standard model-call envelope."""

from .types import Actor


def uses_llm_envelope(actor: Actor) -> bool:
    """Custom wrappers opt in; unrelated policies are never guessed from parameters."""
    return actor.policy_id == "llm.v1" or actor.attributes.get("model_policy") == "llm.v1"
