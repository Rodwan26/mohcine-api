from dataclasses import dataclass
from uuid import UUID

from app.core.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class PriceChanged(DomainEvent):
    product_id: UUID
    old_price: str
    new_price: str
