"""Delayed event and shipment queues for discrete-tick transitions."""

from uuid import uuid4

from pydantic import Field, JsonValue

from simulation_core.types import FrozenModel


class DelayedItem(FrozenModel):
    """An event, shipment, or settlement scheduled for delivery at a future tick."""

    item_id: str = Field(default_factory=lambda: uuid4().hex)
    sender_id: str
    recipient_id: str
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    scheduled_tick: int = Field(ge=0)
    created_tick: int = Field(ge=0)


class DelayedQueue(FrozenModel):
    """Immutable, deterministic delayed-item queue."""

    items: tuple[DelayedItem, ...] = Field(default_factory=tuple)

    @property
    def is_empty(self) -> bool:
        return len(self.items) == 0

    def enqueue(
        self,
        sender_id: str,
        recipient_id: str,
        payload: dict[str, JsonValue],
        *,
        current_tick: int,
        delay_ticks: int,
        item_id: str | None = None,
    ) -> tuple["DelayedQueue", DelayedItem]:
        if delay_ticks < 0:
            raise ValueError("delay_ticks must be non-negative")
        if current_tick < 0:
            raise ValueError("current_tick must be non-negative")
        item = DelayedItem(
            item_id=item_id or uuid4().hex,
            sender_id=sender_id,
            recipient_id=recipient_id,
            payload=payload,
            scheduled_tick=current_tick + delay_ticks,
            created_tick=current_tick,
        )
        return DelayedQueue(items=(*self.items, item)), item

    def drain_due(self, current_tick: int) -> tuple["DelayedQueue", tuple[DelayedItem, ...]]:
        due = tuple(item for item in self.items if item.scheduled_tick <= current_tick)
        remaining = tuple(item for item in self.items if item.scheduled_tick > current_tick)
        return DelayedQueue(items=remaining), due

    def pending_for(self, recipient_id: str) -> tuple[DelayedItem, ...]:
        return tuple(item for item in self.items if item.recipient_id == recipient_id)

    def pending_from(self, sender_id: str) -> tuple[DelayedItem, ...]:
        return tuple(item for item in self.items if item.sender_id == sender_id)
