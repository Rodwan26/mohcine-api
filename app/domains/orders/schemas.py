from uuid import UUID

from pydantic import BaseModel, Field


class OrderItemInput(BaseModel):
    product_id: UUID
    quantity: int = Field(ge=1)


class OrderCreate(BaseModel):
    items: list[OrderItemInput] = Field(min_length=1)
    currency: str = "USD"
    notes: str | None = None
    idempotency_key: str | None = None


class OrderItemResponse(BaseModel):
    id: str
    product_id: str
    product_name: str
    sku: str | None = None
    unit_price: str
    quantity: int
    subtotal: str


class OrderResponse(BaseModel):
    id: str
    user_id: str
    status: str
    currency: str
    subtotal: str
    tax_amount: str | None = None
    shipping_amount: str | None = None
    discount_amount: str | None = None
    total_amount: str
    notes: str | None = None
    idempotency_key: str | None = None
    version_id: int = 1
    created_at: str
    updated_at: str
    items: list[OrderItemResponse] = []


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    next_cursor: str | None = None
    has_more: bool = False
    limit: int = 20
