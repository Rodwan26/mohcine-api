from decimal import Decimal
from uuid import UUID

import pytest

from app.domains.catalog.service import CatalogService
from app.domains.catalog.schemas import ProductCreate, ProductUpdate, CategoryCreate
from app.domains.catalog.repository import ProductSpec, CategorySpec
from app.core.outbox import OutboxStore


class TestProductService:
    async def test_create_product(self, uow, tenant_id):
        svc = CatalogService(uow)
        data = ProductCreate(name="Test Product", price=Decimal("29.99"), quantity=10)
        result = await svc.create_product(tenant_id, data)
        assert result["name"] == "Test Product"
        assert result["slug"] == "test-product"
        assert result["is_active"] is True
        assert "id" in result
        assert UUID(result["id"]) is not None

    async def test_create_product_without_event_bus(self, uow, tenant_id):
        svc = CatalogService(uow)
        data = ProductCreate(name="No Event", price=Decimal("10.00"))
        result = await svc.create_product(tenant_id, data)
        assert result["name"] == "No Event"
        assert result["price"] is None  # no pricing created (no handler)

    async def test_get_product(self, uow, tenant_id):
        svc = CatalogService(uow)
        data = ProductCreate(name="Get Test", price=Decimal("15.99"))
        created = await svc.create_product(tenant_id, data)
        result = await svc.get_product(tenant_id, UUID(created["id"]))
        assert result is not None
        assert result["name"] == "Get Test"
        assert UUID(result["id"]) == UUID(created["id"])

    async def test_get_product_not_found(self, uow, tenant_id):
        svc = CatalogService(uow)
        result = await svc.get_product(tenant_id, UUID("00000000-0000-0000-0000-000000000001"))
        assert result is None

    async def test_update_product(self, uow, tenant_id):
        svc = CatalogService(uow)
        data = ProductCreate(name="Update Test", price=Decimal("20.00"))
        created = await svc.create_product(tenant_id, data)
        update = ProductUpdate(name="Updated Name", version_id=1)
        result = await svc.update_product(tenant_id, UUID(created["id"]), update)
        assert result is not None
        assert result["name"] == "Updated Name"

    async def test_update_product_not_found(self, uow, tenant_id):
        svc = CatalogService(uow)
        update = ProductUpdate(name="Nope", version_id=1)
        result = await svc.update_product(tenant_id, UUID("00000000-0000-0000-0000-000000000001"), update)
        assert result is None

    async def test_delete_product(self, uow, tenant_id):
        svc = CatalogService(uow)
        data = ProductCreate(name="Delete Me", price=Decimal("5.00"))
        created = await svc.create_product(tenant_id, data)
        deleted = await svc.delete_product(tenant_id, UUID(created["id"]))
        assert deleted is True
        result = await svc.get_product(tenant_id, UUID(created["id"]))
        assert result is None

    async def test_delete_product_not_found(self, uow, tenant_id):
        svc = CatalogService(uow)
        deleted = await svc.delete_product(tenant_id, UUID("00000000-0000-0000-0000-000000000001"))
        assert deleted is False

    async def test_list_products_empty(self, uow, tenant_id):
        svc = CatalogService(uow)
        result = await svc.list_products(tenant_id)
        assert result["items"] == []
        assert result["has_more"] is False

    async def test_list_products_with_data(self, uow, tenant_id):
        svc = CatalogService(uow)
        names = ["Alpha", "Bravo", "Charlie"]
        for n in names:
            await svc.create_product(tenant_id, ProductCreate(name=n, price=Decimal("10.00")))
        result = await svc.list_products(tenant_id, limit=2)
        assert len(result["items"]) == 2
        assert result["has_more"] is True
        assert result["next_cursor"] is not None
        # second page
        result2 = await svc.list_products(tenant_id, cursor=result["next_cursor"], limit=2)
        assert len(result2["items"]) == 1
        assert result2["has_more"] is False

    async def test_list_products_search(self, uow, tenant_id):
        svc = CatalogService(uow)
        await svc.create_product(tenant_id, ProductCreate(name="Red Shoe", price=Decimal("10.00")))
        await svc.create_product(tenant_id, ProductCreate(name="Blue Hat", price=Decimal("10.00")))
        spec = ProductSpec(tenant_id=tenant_id, search="shoe")
        result = await svc.list_products(tenant_id, spec)
        assert len(result["items"]) == 1
        assert result["items"][0].name == "Red Shoe"

    async def test_list_products_category_filter(self, uow, tenant_id):
        svc = CatalogService(uow)
        cat = await svc.create_category(tenant_id, CategoryCreate(name="Electronics"))
        cat_id = cat["id"]
        await svc.create_product(tenant_id, ProductCreate(name="Laptop", price=Decimal("999.00"), category_id=cat_id))
        await svc.create_product(tenant_id, ProductCreate(name="Book", price=Decimal("15.00")))
        spec = ProductSpec(tenant_id=tenant_id, category_id=UUID(cat_id))
        result = await svc.list_products(tenant_id, spec)
        assert len(result["items"]) == 1
        assert result["items"][0].name == "Laptop"

    async def test_tenant_isolation(self, uow, db_session, tenant_id):
        """Products from one tenant should not be visible to another."""
        svc = CatalogService(uow)
        await svc.create_product(tenant_id, ProductCreate(name="Tenant A Product", price=Decimal("10.00")))
        await uow.commit()
        result = await svc.list_products(tenant_id)
        assert len(result["items"]) == 1
        # Different tenant
        result_alt = await svc.list_products(UUID("00000000-0000-0000-0000-000000000099"))
        assert len(result_alt["items"]) == 0


class TestCategoryService:
    async def test_create_category(self, uow, tenant_id):
        svc = CatalogService(uow)
        data = CategoryCreate(name="Clothing")
        result = await svc.create_category(tenant_id, data)
        assert result["name"] == "Clothing"
        assert result["slug"] == "clothing"

    async def test_create_category_with_parent(self, uow, tenant_id):
        svc = CatalogService(uow)
        parent = await svc.create_category(tenant_id, CategoryCreate(name="Parent"))
        child = await svc.create_category(tenant_id, CategoryCreate(name="Child", parent_id=parent["id"]))
        assert child["name"] == "Child"
        assert child["parent_id"] == parent["id"]

    async def test_get_category(self, uow, tenant_id):
        svc = CatalogService(uow)
        created = await svc.create_category(tenant_id, CategoryCreate(name="Get Me"))
        result = await svc.get_category(tenant_id, UUID(created["id"]))
        assert result is not None
        assert result["id"] == created["id"]

    async def test_get_category_not_found(self, uow, tenant_id):
        svc = CatalogService(uow)
        result = await svc.get_category(tenant_id, UUID("00000000-0000-0000-0000-000000000001"))
        assert result is None

    async def test_update_category(self, uow, tenant_id):
        from app.domains.catalog.schemas import CategoryUpdate
        svc = CatalogService(uow)
        created = await svc.create_category(tenant_id, CategoryCreate(name="Old Name"))
        update = CategoryUpdate(name="New Name", version_id=1)
        result = await svc.update_category(tenant_id, UUID(created["id"]), update)
        assert result is not None
        assert result["name"] == "New Name"

    async def test_delete_category(self, uow, tenant_id):
        svc = CatalogService(uow)
        created = await svc.create_category(tenant_id, CategoryCreate(name="Delete Me"))
        deleted = await svc.delete_category(tenant_id, UUID(created["id"]))
        assert deleted is True
        result = await svc.get_category(tenant_id, UUID(created["id"]))
        assert result is None

    async def test_category_tree(self, uow, tenant_id):
        svc = CatalogService(uow)
        parent = await svc.create_category(tenant_id, CategoryCreate(name="Root"))
        child = await svc.create_category(tenant_id, CategoryCreate(name="Leaf", parent_id=parent["id"]))
        tree = await svc.get_category_tree()
        assert len(tree) == 1  # tree is tenant-aware
