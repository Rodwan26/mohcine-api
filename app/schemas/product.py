from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, examples=["T-Shirt"])
    description: Optional[str] = None
    category_id: Optional[str] = None
    price: Decimal = Field(gt=0, examples=[29.99])
    compare_at_price: Optional[Decimal] = None
    cost_price: Optional[Decimal] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    quantity: int = 0


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[str] = None
    price: Optional[Decimal] = None
    compare_at_price: Optional[Decimal] = None
    cost_price: Optional[Decimal] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    quantity: Optional[int] = None
    is_active: Optional[bool] = None
    version_id: int = Field(ge=1, description="Required for optimistic locking")


class ProductResponse(BaseModel):
    id: str
    public_id: Optional[str] = None
    name: str
    slug: str
    description: Optional[str] = None
    category_id: Optional[str] = None
    is_active: bool
    price: Optional[str] = None
    compare_at_price: Optional[str] = None
    sku: Optional[str] = None
    quantity: int = 0
    version_id: int = 1
    created_at: str
    updated_at: str


class ProductFilter(BaseModel):
    search: Optional[str] = None
    category_id: Optional[str] = None
    is_active: Optional[bool] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    sort_by: str = "created_at"
    sort_dir: str = "desc"
