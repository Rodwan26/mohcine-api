from uuid import UUID

import pytest

from app.domains.inventory.service import InventoryService, handle_product_created


class TestInventoryService:
    async def test_initialize_inventory(self, uow, tenant_id, product):
        svc = InventoryService(uow)
        await svc.initialize(
            product_id=product.id,
            tenant_id=tenant_id,
            sku="SKU-001",
            quantity=100,
        )
        await uow.commit()
        inv = await svc.get(product.id, tenant_id)
        assert inv is not None
        assert inv.sku == "SKU-001"
        assert inv.quantity == 100
        assert inv.reserved_quantity == 0

    async def test_initialize_without_sku(self, uow, tenant_id, product):
        svc = InventoryService(uow)
        await svc.initialize(product_id=product.id, tenant_id=tenant_id, quantity=50)
        await uow.commit()
        inv = await svc.get(product.id, tenant_id)
        assert inv is not None
        assert inv.sku is None
        assert inv.quantity == 50

    async def test_available_quantity(self, uow, tenant_id, product):
        svc = InventoryService(uow)
        await svc.initialize(product_id=product.id, tenant_id=tenant_id, quantity=100)
        await uow.commit()
        avail = await svc.get_available(product.id, tenant_id)
        assert avail == 100

    async def test_reserve_success(self, uow, tenant_id, product):
        svc = InventoryService(uow)
        await svc.initialize(product_id=product.id, tenant_id=tenant_id, quantity=50)
        await uow.commit()
        ok = await svc.reserve(product.id, tenant_id, 10, "res-001")
        assert ok is True
        avail = await svc.get_available(product.id, tenant_id)
        assert avail == 40
        inv = await svc.get(product.id, tenant_id)
        assert inv.reserved_quantity == 10

    async def test_reserve_insufficient_stock(self, uow, tenant_id, product):
        svc = InventoryService(uow)
        await svc.initialize(product_id=product.id, tenant_id=tenant_id, quantity=5)
        await uow.commit()
        ok = await svc.reserve(product.id, tenant_id, 10, "res-002")
        assert ok is False
        avail = await svc.get_available(product.id, tenant_id)
        assert avail == 5

    async def test_reserve_nonexistent_product(self, uow, tenant_id):
        svc = InventoryService(uow)
        ok = await svc.reserve(
            UUID("00000000-0000-0000-0000-000000000099"), tenant_id, 1, "res-003",
        )
        assert ok is False

    async def test_commit_sale(self, uow, tenant_id, product):
        svc = InventoryService(uow)
        await svc.initialize(product_id=product.id, tenant_id=tenant_id, quantity=100)
        await uow.commit()
        ok = await svc.reserve(product.id, tenant_id, 30, "res-commit-1")
        assert ok is True
        await uow.commit()
        await svc.commit_sale(product.id, tenant_id, 30, "sale-001")
        await uow.commit()
        inv = await svc.get(product.id, tenant_id)
        assert inv.quantity == 70
        assert inv.reserved_quantity == 0

    async def test_commit_sale_without_reservation(self, uow, tenant_id, product):
        """Direct commit sale (skip reservation) should work."""
        svc = InventoryService(uow)
        await svc.initialize(product_id=product.id, tenant_id=tenant_id, quantity=50)
        await uow.commit()
        await svc.commit_sale(product.id, tenant_id, 5, "sale-direct-001")
        await uow.commit()
        inv = await svc.get(product.id, tenant_id)
        assert inv.quantity == 45

    async def test_release_reservation(self, uow, tenant_id, product):
        svc = InventoryService(uow)
        await svc.initialize(product_id=product.id, tenant_id=tenant_id, quantity=100)
        await uow.commit()
        ok = await svc.reserve(product.id, tenant_id, 40, "res-release-1")
        assert ok is True
        await uow.commit()
        await svc.release(product.id, tenant_id, 40, "rel-001")
        await uow.commit()
        inv = await svc.get(product.id, tenant_id)
        assert inv.reserved_quantity == 0
        assert inv.quantity == 100

    async def test_idempotent_reserve(self, uow, tenant_id, product):
        """Same idempotency_key should not double-reserve."""
        svc = InventoryService(uow)
        await svc.initialize(product_id=product.id, tenant_id=tenant_id, quantity=100)
        await uow.commit()

        ok1 = await svc.reserve(product.id, tenant_id, 10, "idem-res-1")
        assert ok1 is True
        await uow.commit()

        ok2 = await svc.reserve(product.id, tenant_id, 10, "idem-res-1")
        assert ok2 is True
        await uow.commit()

        inv = await svc.get(product.id, tenant_id)
        assert inv.reserved_quantity == 10  # not 20

    async def test_idempotent_commit_sale(self, uow, tenant_id, product):
        """Same idempotency_key should not double-commit."""
        svc = InventoryService(uow)
        await svc.initialize(product_id=product.id, tenant_id=tenant_id, quantity=50)
        await uow.commit()

        await svc.commit_sale(product.id, tenant_id, 10, "idem-sale-1")
        await uow.commit()

        await svc.commit_sale(product.id, tenant_id, 10, "idem-sale-1")
        await uow.commit()

        inv = await svc.get(product.id, tenant_id)
        assert inv.quantity == 40  # not 30

    async def test_idempotent_release(self, uow, tenant_id, product):
        """Same idempotency_key should not double-release."""
        svc = InventoryService(uow)
        await svc.initialize(product_id=product.id, tenant_id=tenant_id, quantity=100)
        await uow.commit()
        await svc.reserve(product.id, tenant_id, 30, "idem-rel-res-1")
        await uow.commit()

        await svc.release(product.id, tenant_id, 30, "idem-rel-1")
        await uow.commit()
        await svc.release(product.id, tenant_id, 30, "idem-rel-1")
        await uow.commit()

        inv = await svc.get(product.id, tenant_id)
        assert inv.reserved_quantity == 0

    async def test_get_nonexistent(self, uow, tenant_id):
        svc = InventoryService(uow)
        inv = await svc.get(UUID("00000000-0000-0000-0000-000000000099"), tenant_id)
        assert inv is None

    async def test_get_available_nonexistent(self, uow, tenant_id):
        svc = InventoryService(uow)
        avail = await svc.get_available(UUID("00000000-0000-0000-0000-000000000099"), tenant_id)
        assert avail == 0

    async def test_adjust_quantity(self, uow, tenant_id, product):
        svc = InventoryService(uow)
        await svc.initialize(product_id=product.id, tenant_id=tenant_id, quantity=100)
        await uow.commit()
        await svc.adjust_quantity(product.id, tenant_id, 200)
        await uow.commit()
        inv = await svc.get(product.id, tenant_id)
        assert inv.quantity == 200


class TestInventoryHandler:
    async def test_handle_product_created(self, tenant_id, test_session_factory):
        from uuid import uuid4
        product_id = UUID("00000000-0000-0000-0000-000000000100")

        from app.domains.catalog.models import Product
        async with test_session_factory() as session:
            p = Product(id=product_id, tenant_id=tenant_id,
                        name="handler-inv", slug="handler-inv",
                        created_by=uuid4())
            session.add(p)
            await session.commit()

        await handle_product_created({
            "tenant_id": str(tenant_id),
            "product_id": str(product_id),
            "sku": "SKU-HANDLER",
            "quantity": 75,
        }, test_session_factory)

        from app.domains.inventory.models import ProductInventory
        from sqlalchemy import select
        async with test_session_factory() as session:
            result = await session.execute(
                select(ProductInventory).where(ProductInventory.product_id == product_id)
            )
            inv = result.scalar_one_or_none()
            assert inv is not None
            assert inv.sku == "SKU-HANDLER"
            assert inv.quantity == 75
