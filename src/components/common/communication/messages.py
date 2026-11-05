"""Communication action payloads and privacy-preserving message router."""

from uuid import uuid4

from pydantic import Field, JsonValue

from simulation_core.types import FrozenModel, PrivateState


class PublicBroadcastPayload(FrozenModel):
    """Action payload for broadcasting a message to all actors."""

    content: str = Field(min_length=1, max_length=2000)
    topic: str = "general"
    data: dict[str, JsonValue] = Field(default_factory=dict)


class DirectMessagePayload(FrozenModel):
    """Action payload for sending a private message to a specific actor."""

    recipient_id: str = Field(min_length=1)
    content: str = Field(min_length=1, max_length=2000)
    topic: str = "direct"
    data: dict[str, JsonValue] = Field(default_factory=dict)


class Message(FrozenModel):
    """Canonical message record in public or private state."""

    message_id: str = Field(default_factory=lambda: uuid4().hex)
    sender_id: str
    recipient_id: str | None = None
    topic: str = "general"
    content: str
    tick: int = Field(ge=0)
    data: dict[str, JsonValue] = Field(default_factory=dict)


def route_message(
    message: Message,
    public_facts: dict[str, JsonValue],
    private_states: dict[str, PrivateState],
) -> tuple[dict[str, JsonValue], dict[str, PrivateState]]:
    """Route a message to public broadcasts or strictly isolated recipient inbox.

    Guarantees that direct messages between sender and recipient are never visible
    in public facts or to third-party actors.
    """
    updated_public = dict(public_facts)
    updated_private = {aid: state.model_copy(deep=True) for aid, state in private_states.items()}

    msg_dict = message.model_dump(mode="json")

    if message.recipient_id is None:
        # Public broadcast
        raw_broadcasts = updated_public.get("broadcasts")
        broadcasts = list(raw_broadcasts) if isinstance(raw_broadcasts, list) else []
        broadcasts.append(msg_dict)
        updated_public["broadcasts"] = broadcasts
    else:
        # Targeted direct message
        recipient_id = message.recipient_id
        if recipient_id not in updated_private:
            raise ValueError(f"Unknown message recipient: {recipient_id}")
        raw_inbox = updated_private[recipient_id].facts.get("inbox")
        recipient_inbox = list(raw_inbox) if isinstance(raw_inbox, list) else []
        recipient_inbox.append(msg_dict)
        updated_private[recipient_id] = PrivateState(
            facts={**updated_private[recipient_id].facts, "inbox": recipient_inbox},
            memory=updated_private[recipient_id].memory,
        )

        # Record in sender's private outbox
        sender_id = message.sender_id
        if sender_id in updated_private:
            raw_outbox = updated_private[sender_id].facts.get("outbox")
            sender_outbox = list(raw_outbox) if isinstance(raw_outbox, list) else []
            sender_outbox.append(msg_dict)
            updated_private[sender_id] = PrivateState(
                facts={**updated_private[sender_id].facts, "outbox": sender_outbox},
                memory=updated_private[sender_id].memory,
            )

    return updated_public, updated_private
