from sqlalchemy import Select

from app.core.repository import TenantRepository
from app.core.specification import Specification
from app.domains.catalog.models import Product, Category


class ProductRepository(TenantRepository):
    def __init__(self, session):
        super().__init__(Product, session)


class CategoryRepository(TenantRepository):
    def __init__(self, session):
        super().__init__(Category, session)

    async def get_tree(self) -> list:
        from sqlalchemy import select
        stmt = self.query().order_by(Category.sort_order)
        all_cats = await self.find_many(stmt)
        return self._build_tree(all_cats)

    def _build_tree(self, categories: list, parent_id=None) -> list:
        tree = []
        for cat in categories:
            if cat.parent_id == parent_id:
                children = self._build_tree(categories, cat.id)
                tree.append({**cat.__dict__, "children": children})
        return tree


class ProductSpec(Specification):
    def __init__(
        self,
        tenant_id=None,
        search=None,
        category_id=None,
        is_active=None,
        price_min=None,
        price_max=None,
        sort_by="created_at",
        sort_dir="desc",
    ):
        from uuid import UUID
        self.tenant_id = tenant_id if isinstance(tenant_id, UUID) else (UUID(tenant_id) if tenant_id else None)
        self.search = search
        self.category_id = category_id if isinstance(category_id, UUID) else (UUID(category_id) if category_id else None)
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


class CategorySpec(Specification):
    def __init__(self, tenant_id=None, search=None, is_active=None, parent_id=None,
                 sort_by="sort_order", sort_dir="asc"):
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
