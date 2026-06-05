from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.core.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class PaymentCreated(DomainEvent):
    payment_id: UUID
    order_id: UUID
    amount: Decimal
    currency: str


@dataclass(frozen=True, kw_only=True)
class PaymentSucceeded(DomainEvent):
    payment_id: UUID
    order_id: UUID
    provider_reference: str | None = None


@dataclass(frozen=True, kw_only=True)
class PaymentFailed(DomainEvent):
    payment_id: UUID
    order_id: UUID
    reason: str | None = None


@dataclass(frozen=True, kw_only=True)
class PaymentRefunded(DomainEvent):
    payment_id: UUID
    order_id: UUID
