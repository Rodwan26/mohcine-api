import json
from uuid import UUID

from app.repositories.product_repo import (
    ProductRepository,
    ProductPricingRepository,
    ProductInventoryRepository,
    ProductVariantRepository,
)
from app.repositories.inventory_repo import InventoryTransactionRepository
from app.schemas.product import ProductCreate, ProductUpdate
from app.specifications.product_spec import ProductSpec
from app.core.uow import UnitOfWork
from app.core.slug import generate_slug
from app.core.events import ProductCreated, ProductUpdated, ProductDeleted, EventPublisher
from app.models.product import Product
from app.models.product_inventory import ProductInventory
from app.models.product_pricing import ProductPricing


class ProductService:
    def __init__(self, uow: UnitOfWork, event_bus: EventPublisher | None = None):
        self.uow = uow
        self.event_bus = event_bus
        self.repo = ProductRepository(uow.session)
        self.pricing_repo = ProductPricingRepository(uow.session)
        self.inventory_repo = ProductInventoryRepository(uow.session)
        self.variant_repo = ProductVariantRepository(uow.session)
        self.inv_txn_repo = InventoryTransactionRepository(uow.session)

    async def create(self, tenant_id: UUID, data: ProductCreate) -> dict:
        slug = await generate_slug(data.name, Product, self.uow.session, tenant_id)
        product = await self.repo.create(
            tenant_id=tenant_id,
            name=data.name,
            slug=slug,
            description=data.description,
            category_id=UUID(data.category_id) if data.category_id else None,
        )
        await self.pricing_repo.create(
            product_id=product.id,
            tenant_id=tenant_id,
            price=str(data.price),
            compare_at_price=str(data.compare_at_price) if data.compare_at_price else None,
            cost_price=str(data.cost_price) if data.cost_price else None,
        )
        await self.inventory_repo.create(
            product_id=product.id,
            tenant_id=tenant_id,
            sku=data.sku,
            barcode=data.barcode,
            quantity=data.quantity,
        )
        if data.quantity > 0:
            await self.inv_txn_repo.create(
                tenant_id=tenant_id,
                product_id=product.id,
                type="purchase",
                quantity_change=data.quantity,
                running_balance=data.quantity,
                note="Initial stock",
            )
        await self.uow.commit()
        event = ProductCreated(product_id=product.id, name=product.name, tenant_id=tenant_id)
        if self.event_bus:
            await self.event_bus.publish(event)
        return await self.get(tenant_id, product.id)

    async def update(self, tenant_id: UUID, product_id: UUID, data: ProductUpdate) -> dict | None:
        product = await self.repo.find_one(tenant_id=tenant_id, id=product_id)
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
            await self.repo.update(product, **update)
        if data.price is not None:
            pricing = await self.pricing_repo.find_one(product_id=product_id, tenant_id=tenant_id)
            if pricing:
                await self.pricing_repo.update(pricing, price=str(data.price))
        if data.quantity is not None:
            inv = await self.inventory_repo.find_one(product_id=product_id, tenant_id=tenant_id)
            if inv:
                old_qty = inv.quantity
                await self.inventory_repo.update(inv, quantity=data.quantity)
                diff = data.quantity - old_qty
                if diff != 0:
                    await self.inv_txn_repo.create(
                        tenant_id=tenant_id,
                        product_id=product_id,
                        type="adjustment",
                        quantity_change=diff,
                        running_balance=data.quantity,
                        note="Manual adjustment",
                    )
        await self.uow.commit()
        event = ProductUpdated(product_id=product.id, name=product.name, tenant_id=tenant_id)
        if self.event_bus:
            await self.event_bus.publish(event)
        return await self.get(tenant_id, product_id)

    async def get(self, tenant_id: UUID, product_id: UUID) -> dict | None:
        product = await self.repo.find_one(tenant_id=tenant_id, id=product_id)
        if not product:
            return None
        pricing = await self.pricing_repo.find_one(product_id=product_id, tenant_id=tenant_id)
        inventory = await self.inventory_repo.find_one(product_id=product_id, tenant_id=tenant_id)
        return self._to_response(product, pricing, inventory)

    async def list(
        self,
        tenant_id: UUID,
        spec: ProductSpec | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> dict:
        s = spec or ProductSpec(tenant_id=tenant_id)
        stmt = s.apply(self.repo.query())
        return await self.repo.cursor_paginate(stmt, cursor=cursor, limit=limit)

    async def delete(self, tenant_id: UUID, product_id: UUID) -> bool:
        product = await self.repo.find_one(tenant_id=tenant_id, id=product_id)
        if not product:
            return False
        await self.repo.soft_delete(product)
        await self.uow.commit()
        event = ProductDeleted(product_id=product.id, tenant_id=tenant_id)
        if self.event_bus:
            await self.event_bus.publish(event)
        return True

    def _to_response(self, product, pricing=None, inventory=None) -> dict:
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
