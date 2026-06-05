from dataclasses import dataclass
from uuid import UUID

from app.core.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class OrderItemReservation:
    product_id: str
    quantity: int


@dataclass(frozen=True, kw_only=True)
class OrderCreated(DomainEvent):
    order_id: UUID
    user_id: UUID
    items: list
    currency: str = "USD"
    notes: str | None = None


@dataclass(frozen=True, kw_only=True)
class OrderConfirmed(DomainEvent):
    order_id: UUID


@dataclass(frozen=True, kw_only=True)
class OrderStatusChanged(DomainEvent):
    order_id: UUID
    old_status: str
    new_status: str


@dataclass(frozen=True, kw_only=True)
class OrderCancelled(DomainEvent):
    order_id: UUID
    reason: str | None = None
