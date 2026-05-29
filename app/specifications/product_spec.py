from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import Select

from app.core.specification import Specification
from app.models.product import Product


class ProductSpec(Specification):
    def __init__(
        self,
        tenant_id: UUID | None = None,
        search: str | None = None,
        category_id: UUID | None = None,
        is_active: bool | None = None,
        price_min: float | None = None,
        price_max: float | None = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
    ):
        from uuid import UUID as UUIDType
        self.tenant_id = tenant_id if isinstance(tenant_id, UUIDType) else (UUID(tenant_id) if tenant_id else None)
        self.search = search
        self.category_id = category_id if isinstance(category_id, UUIDType) else (UUID(category_id) if category_id else None)
        self.is_active = is_active
        self.price_min = price_min
        self.price_max = price_max
        self.sort_by = sort_by if sort_by in ("created_at", "name", "updated_at") else "created_at"
        self.sort_dir = sort_dir if sort_dir in ("asc", "desc") else "desc"

    def filters(self, query: Select) -> Select:
        if self.tenant_id:
            query = query.where(Product.tenant_id == self.tenant_id)
        if self.search:
            query = query.where(Product.name.ilike(f"%{self.search}%"))
        if self.category_id:
            query = query.where(Product.category_id == self.category_id)
        if self.is_active is not None:
            query = query.where(Product.is_active == self.is_active)
        return query

    def ordering(self, query: Select) -> Select:
        sort_col = getattr(Product, self.sort_by)
        order_fn = sort_col.desc if self.sort_dir == "desc" else sort_col.asc
        return query.order_by(order_fn(), Product.id.desc())
