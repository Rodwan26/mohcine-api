from typing import Optional
from uuid import UUID

from sqlalchemy import Select

from app.core.specification import Specification
from app.models.category import Category


class CategorySpec(Specification):
    def __init__(
        self,
        tenant_id: UUID | None = None,
        search: str | None = None,
        is_active: bool | None = None,
        parent_id: UUID | None = None,
        sort_by: str = "sort_order",
        sort_dir: str = "asc",
    ):
        self.tenant_id = tenant_id
        self.search = search
        self.is_active = is_active
        self.parent_id = parent_id
        self.sort_by = sort_by if sort_by in ("sort_order", "name", "created_at") else "sort_order"
        self.sort_dir = sort_dir if sort_dir in ("asc", "desc") else "asc"

    def filters(self, query: Select) -> Select:
        if self.tenant_id:
            query = query.where(Category.tenant_id == self.tenant_id)
        if self.search:
            query = query.where(Category.name.ilike(f"%{self.search}%"))
        if self.is_active is not None:
            query = query.where(Category.is_active == self.is_active)
        if self.parent_id is not None:
            query = query.where(Category.parent_id == self.parent_id)
        return query

    def ordering(self, query: Select) -> Select:
        sort_col = getattr(Category, self.sort_by)
        order_fn = sort_col.desc if self.sort_dir == "desc" else sort_col.asc
        return query.order_by(order_fn())
