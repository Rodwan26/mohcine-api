from uuid import UUID
from decimal import Decimal

from pydantic import BaseModel, Field


class PaymentCreate(BaseModel):
    order_id: UUID
    amount: Decimal = Field(gt=0)
    currency: str = "USD"
    provider: str | None = None
    provider_reference: str | None = None
    idempotency_key: str | None = None


class PaymentResponse(BaseModel):
    id: str
    order_id: str
    amount: str
    currency: str
    status: str
    provider: str | None = None
    provider_reference: str | None = None
    idempotency_key: str | None = None
    version_id: int = 1
    created_at: str
    updated_at: str
