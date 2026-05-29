from dataclasses import dataclass
from uuid import UUID

from app.core.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class StockChanged(DomainEvent):
    product_id: UUID
    old_quantity: int
    new_quantity: int
    reason: str
