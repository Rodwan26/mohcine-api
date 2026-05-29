from dataclasses import dataclass
from uuid import UUID

from app.core.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class ProductCreated(DomainEvent):
    product_id: UUID
    name: str
    price: str | None = None
    compare_at_price: str | None = None
    sku: str | None = None
    quantity: int = 0


@dataclass(frozen=True, kw_only=True)
class ProductUpdated(DomainEvent):
    product_id: UUID
    name: str
    price: str | None = None


@dataclass(frozen=True, kw_only=True)
class ProductDeleted(DomainEvent):
    product_id: UUID


@dataclass(frozen=True, kw_only=True)
class CategoryCreated(DomainEvent):
    category_id: UUID
    name: str


@dataclass(frozen=True, kw_only=True)
class CategoryUpdated(DomainEvent):
    category_id: UUID
    name: str


@dataclass(frozen=True, kw_only=True)
class CategoryDeleted(DomainEvent):
    category_id: UUID
