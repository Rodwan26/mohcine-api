from sqlalchemy import select

from app.core.repository import TenantRepository
from app.models.category import Category


class CategoryRepository(TenantRepository):
    def __init__(self, session):
        super().__init__(Category, session)

    async def get_tree(self) -> list:
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
