from uuid import UUID

from sqlalchemy import select

from app.domains.catalog.models import Product, Category
from app.domains.catalog.repository import ProductRepository, CategoryRepository, ProductSpec, CategorySpec
from app.domains.catalog.events import (
    ProductCreated, ProductUpdated, ProductDeleted,
    CategoryCreated, CategoryUpdated, CategoryDeleted,
)
from app.core.events import EventPublisher
from app.domains.catalog.schemas import ProductCreate, ProductUpdate
from app.core.uow import UnitOfWork
from app.core.slug import generate_slug


class CatalogService:
    def __init__(self, uow: UnitOfWork, event_bus: EventPublisher | None = None):
        self.uow = uow
        self.event_bus = event_bus
        self.product_repo = ProductRepository(uow.session)
        self.category_repo = CategoryRepository(uow.session)

    async def create_product(self, tenant_id: UUID, data: ProductCreate) -> dict:
        slug = await generate_slug(data.name, Product, self.uow.session, tenant_id)
        product = await self.product_repo.create(
            tenant_id=tenant_id,
            name=data.name,
            slug=slug,
            description=data.description,
            category_id=UUID(data.category_id) if data.category_id else None,
        )
        await self.uow.commit()

        if self.event_bus:
            await self.event_bus.publish(ProductCreated(
                product_id=product.id,
                tenant_id=tenant_id,
                name=data.name,
                price=str(data.price),
                compare_at_price=str(data.compare_at_price) if data.compare_at_price else None,
                sku=data.sku,
                quantity=data.quantity,
            ))
        return await self.get_product(tenant_id, product.id)

    async def update_product(self, tenant_id: UUID, product_id: UUID, data: ProductUpdate) -> dict | None:
        product = await self.product_repo.find_one(tenant_id=tenant_id, id=product_id)
        if not product:
            return None
        update = {}
        for f in ("name", "description", "is_active"):
            v = getattr(data, f, None)
            if v is not None:
                update[f] = v
        if data.category_id is not None:
            update["category_id"] = UUID(data.category_id)
        if data.name and data.name != product.name:
            update["slug"] = await generate_slug(data.name, Product, self.uow.session, tenant_id)
        if update:
            await self.product_repo.update(product, **update)
            await self.uow.commit()

        if self.event_bus:
            await self.event_bus.publish(ProductUpdated(
                product_id=product.id,
                tenant_id=tenant_id,
                name=data.name or product.name,
                price=str(data.price) if data.price else None,
            ))
        return await self.get_product(tenant_id, product_id)

    async def get_product(self, tenant_id: UUID, product_id: UUID) -> dict | None:
        product = await self.product_repo.find_one(tenant_id=tenant_id, id=product_id)
        if not product:
            return None
        pricing = await self._read_pricing(product_id, tenant_id)
        inventory = await self._read_inventory(product_id, tenant_id)
        return self._product_to_response(product, pricing, inventory)

    async def list_products(self, tenant_id: UUID, spec: ProductSpec | None = None,
                            cursor: str | None = None, limit: int = 20) -> dict:
        s = spec or ProductSpec(tenant_id=tenant_id)
        stmt = s.apply(self.product_repo.query())
        return await self.product_repo.cursor_paginate(stmt, cursor=cursor, limit=limit)

    async def delete_product(self, tenant_id: UUID, product_id: UUID) -> bool:
        product = await self.product_repo.find_one(tenant_id=tenant_id, id=product_id)
        if not product:
            return False
        await self.product_repo.soft_delete(product)
        await self.uow.commit()
        if self.event_bus:
            await self.event_bus.publish(ProductDeleted(product_id=product.id, tenant_id=tenant_id))
        return True

    async def create_category(self, tenant_id: UUID, data) -> dict:
        slug = await generate_slug(data.name, Category, self.uow.session, tenant_id)
        category = await self.category_repo.create(
            tenant_id=tenant_id,
            name=data.name,
            slug=slug,
            description=data.description,
            parent_id=UUID(data.parent_id) if data.parent_id else None,
            sort_order=data.sort_order,
            image=data.image,
        )
        await self.uow.commit()
        if self.event_bus:
            await self.event_bus.publish(CategoryCreated(
                category_id=category.id, name=category.name, tenant_id=tenant_id))
        return self._category_to_response(category)

    async def update_category(self, tenant_id: UUID, category_id: UUID, data) -> dict | None:
        category = await self.category_repo.find_one(tenant_id=tenant_id, id=category_id)
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
            await self.category_repo.update(category, **update)
            await self.uow.commit()
        if self.event_bus:
            await self.event_bus.publish(CategoryUpdated(
                category_id=category.id, name=category.name, tenant_id=tenant_id))
        return await self.get_category(tenant_id, category_id)

    async def get_category(self, tenant_id: UUID, category_id: UUID) -> dict | None:
        category = await self.category_repo.find_one(tenant_id=tenant_id, id=category_id)
        return self._category_to_response(category) if category else None

    async def list_categories(self, tenant_id: UUID, spec: CategorySpec | None = None) -> list:
        s = spec or CategorySpec(tenant_id=tenant_id)
        stmt = s.apply(self.category_repo.query())
        categories = await self.category_repo.find_many(stmt)
        return [self._category_to_response(c) for c in categories]

    async def get_category_tree(self) -> list:
        return await self.category_repo.get_tree()

    async def delete_category(self, tenant_id: UUID, category_id: UUID) -> bool:
        category = await self.category_repo.find_one(tenant_id=tenant_id, id=category_id)
        if not category:
            return False
        await self.category_repo.soft_delete(category)
        await self.uow.commit()
        if self.event_bus:
            await self.event_bus.publish(CategoryDeleted(
                category_id=category.id, tenant_id=tenant_id))
        return True

    async def _read_pricing(self, product_id: UUID, tenant_id: UUID):
        from app.domains.pricing.models import ProductPricing
        result = await self.uow.session.execute(
            select(ProductPricing).where(
                ProductPricing.product_id == product_id,
                ProductPricing.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def _read_inventory(self, product_id: UUID, tenant_id: UUID):
        from app.domains.inventory.models import ProductInventory
        result = await self.uow.session.execute(
            select(ProductInventory).where(
                ProductInventory.product_id == product_id,
                ProductInventory.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    def _product_to_response(self, product, pricing=None, inventory=None) -> dict:
        return {
            "id": str(product.id),
            "public_id": product.public_id,
            "name": product.name,
            "slug": product.slug,
            "description": product.description,
            "category_id": str(product.category_id) if product.category_id else None,
            "is_active": product.is_active,
            "price": str(pricing.price) if pricing else None,
            "compare_at_price": str(pricing.compare_at_price) if pricing and pricing.compare_at_price else None,
            "sku": inventory.sku if inventory else None,
            "quantity": inventory.quantity if inventory else 0,
            "version_id": getattr(product, "version_id", 1),
            "created_at": product.created_at.isoformat(),
            "updated_at": product.updated_at.isoformat(),
        }

    def _category_to_response(self, category) -> dict:
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
