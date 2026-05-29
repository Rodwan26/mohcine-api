from uuid import UUID

from app.repositories.category_repo import CategoryRepository
from app.repositories.inventory_repo import InventoryTransactionRepository
from app.schemas.category import CategoryCreate, CategoryUpdate
from app.specifications.category_spec import CategorySpec
from app.core.uow import UnitOfWork
from app.core.slug import generate_slug
from app.core.events import CategoryCreated, CategoryUpdated, CategoryDeleted, EventPublisher
from app.models.category import Category


class CategoryService:
    def __init__(self, uow: UnitOfWork, event_bus: EventPublisher | None = None):
        self.uow = uow
        self.event_bus = event_bus
        self.repo = CategoryRepository(uow.session)

    async def create(self, tenant_id: UUID, data: CategoryCreate) -> dict:
        slug = await generate_slug(data.name, Category, self.uow.session, tenant_id)
        category = await self.repo.create(
            tenant_id=tenant_id,
            name=data.name,
            slug=slug,
            description=data.description,
            parent_id=UUID(data.parent_id) if data.parent_id else None,
            sort_order=data.sort_order,
            image=data.image,
        )
        await self.uow.commit()
        event = CategoryCreated(category_id=category.id, name=category.name, tenant_id=tenant_id)
        if self.event_bus:
            await self.event_bus.publish(event)
        return self._to_response(category)

    async def update(self, tenant_id: UUID, category_id: UUID, data: CategoryUpdate) -> dict | None:
        category = await self.repo.find_one(tenant_id=tenant_id, id=category_id)
        if not category:
            return None
        update = {}
        for f in ("name", "description", "sort_order", "image", "is_active"):
            v = getattr(data, f, None)
            if v is not None:
                update[f] = v
        if data.parent_id is not None:
            update["parent_id"] = UUID(data.parent_id)
        if data.name and data.name != category.name:
            update["slug"] = await generate_slug(data.name, Category, self.uow.session, tenant_id)
        if update:
            await self.repo.update(category, **update)
            await self.uow.commit()
        event = CategoryUpdated(category_id=category.id, name=category.name, tenant_id=tenant_id)
        if self.event_bus:
            await self.event_bus.publish(event)
        return self._to_response(category)

    async def get(self, tenant_id: UUID, category_id: UUID) -> dict | None:
        category = await self.repo.find_one(tenant_id=tenant_id, id=category_id)
        return self._to_response(category) if category else None

    async def list(self, tenant_id: UUID, spec: CategorySpec | None = None) -> list:
        s = spec or CategorySpec(tenant_id=tenant_id)
        stmt = s.apply(self.repo.query())
        categories = await self.repo.find_many(stmt)
        return [self._to_response(c) for c in categories]

    async def get_tree(self) -> list:
        return await self.repo.get_tree()

    async def delete(self, tenant_id: UUID, category_id: UUID) -> bool:
        category = await self.repo.find_one(tenant_id=tenant_id, id=category_id)
        if not category:
            return False
        await self.repo.soft_delete(category)
        await self.uow.commit()
        event = CategoryDeleted(category_id=category.id, tenant_id=tenant_id)
        if self.event_bus:
            await self.event_bus.publish(event)
        return True

    def _to_response(self, category) -> dict:
        return {
            "id": str(category.id),
            "public_id": category.public_id,
            "name": category.name,
            "slug": category.slug,
            "description": category.description,
            "parent_id": str(category.parent_id) if category.parent_id else None,
            "sort_order": category.sort_order,
            "image": category.image,
            "is_active": category.is_active,
            "version_id": getattr(category, "version_id", 1),
            "created_at": category.created_at.isoformat(),
            "updated_at": category.updated_at.isoformat(),
        }
