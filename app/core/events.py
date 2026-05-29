from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class EventStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    event_id: UUID = field(default_factory=uuid4)
    event_name: str = ""
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tenant_id: UUID | None = None

    def __post_init__(self):
        object.__setattr__(self, "event_name", type(self).__name__)


EventHandler = Any


class EventPublisher:
    async def publish(self, event: DomainEvent) -> None:
        ...

    def subscribe(self, event_type: type, handler: EventHandler) -> None:
        ...


class InMemoryAsyncEventBus(EventPublisher):
    """Dev-only: dispatches handlers inline. Not for production use."""

    def __init__(self):
        self._handlers: dict[str, list[EventHandler]] = {}

    def subscribe(self, event_type: type, handler: EventHandler) -> None:
        name = event_type.__name__
        if name not in self._handlers:
            self._handlers[name] = []
        self._handlers[name].append(handler)

    async def publish(self, event: DomainEvent) -> None:
        handlers = self._handlers.get(event.event_name, [])
        for handler in handlers:
            await handler(event)
