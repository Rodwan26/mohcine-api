from typing import Optional

from pydantic import BaseModel, Field


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, examples=["Clothing"])
    description: Optional[str] = None
    parent_id: Optional[str] = None
    sort_order: int = 0
    image: Optional[str] = None


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[str] = None
    sort_order: Optional[int] = None
    image: Optional[str] = None
    is_active: Optional[bool] = None
    version_id: int = Field(ge=1, description="Required for optimistic locking")


class CategoryResponse(BaseModel):
    id: str
    public_id: Optional[str] = None
    name: str
    slug: str
    description: Optional[str] = None
    parent_id: Optional[str] = None
    sort_order: int
    image: Optional[str] = None
    is_active: bool
    version_id: int = 1
    created_at: str
    updated_at: str
    children: list = []
