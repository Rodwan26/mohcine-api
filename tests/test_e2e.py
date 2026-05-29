from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.core.outbox import OutboxStore, OutboxWorker
from app.domains.catalog.service import CatalogService
from app.domains.catalog.schemas import ProductCreate
from app.domains.pricing.service import handle_product_created as pricing_handler
from app.domains.inventory.service import handle_product_created as inventory_handler
from app.domains.pricing.models import ProductPricing
from app.domains.inventory.models import ProductInventory
from app.models.event_outbox import EventOutbox


@pytest.mark.asyncio
async def test_product_created_flow_end_to_end(db_engine, tenant_id, test_session_factory, uow):
    """Full flow: create product → outbox → worker processes → pricing + inventory rows exist."""
    # 1. Create product with outbox
    outbox = OutboxStore(uow.session)
    svc = CatalogService(uow, event_bus=outbox)
    data = ProductCreate(
        name="E2E Product",
        price=Decimal("49.99"),
        compare_at_price=Decimal("59.99"),
        sku="E2E-SKU",
        quantity=200,
    )
    result = await svc.create_product(tenant_id, data)
    product_id = UUID(result["id"])
    await uow.commit()

    # 2. Verify outbox row exists
    async with test_session_factory() as session:
        result = await session.execute(
            select(EventOutbox).where(EventOutbox.event_name == "ProductCreated")
        )
        rows = list(result.scalars().all())
        assert len(rows) == 1
        outbox_row = rows[0]
        assert outbox_row.status == "pending"

    # 3. Run outbox worker manually
    factory = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False,
    )
    worker = OutboxWorker(
        session_factory=factory,
        handlers={
            "ProductCreated": [pricing_handler, inventory_handler],
        },
    )
    processed = await worker.process_once()
    assert processed == 1

    # 4. Verify pricing and inventory rows created
    async with test_session_factory() as session:
        pricing_result = await session.execute(
            select(ProductPricing).where(ProductPricing.product_id == product_id)
        )
        pricing = pricing_result.scalar_one_or_none()
        assert pricing is not None
        assert str(pricing.price) == "49.99"
        assert str(pricing.compare_at_price) == "59.99"

        inv_result = await session.execute(
            select(ProductInventory).where(ProductInventory.product_id == product_id)
        )
        inv = inv_result.scalar_one_or_none()
        assert inv is not None
        assert inv.sku == "E2E-SKU"
        assert inv.quantity == 200

    # 5. Verify outbox row is marked completed
    async with test_session_factory() as session:
        result = await session.execute(
            select(EventOutbox).where(EventOutbox.id == outbox_row.id)
        )
        row = result.scalar_one()
        assert row.status == "completed"
        assert row.processed_at is not None


@pytest.mark.asyncio
async def test_product_created_idempotent_handlers(db_engine, tenant_id, test_session_factory, uow):
    """Running the worker twice should not create duplicate pricing/inventory rows."""
    outbox = OutboxStore(uow.session)
    svc = CatalogService(uow, event_bus=outbox)
    data = ProductCreate(name="Idempotent", price=Decimal("10.00"), sku="IDEM", quantity=10)
    result = await svc.create_product(tenant_id, data)
    product_id = UUID(result["id"])
    await uow.commit()

    factory = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False,
    )
    worker = OutboxWorker(
        session_factory=factory,
        handlers={
            "ProductCreated": [pricing_handler, inventory_handler],
        },
    )
    processed1 = await worker.process_once()
    assert processed1 == 1

    # Run again — outbox row is already completed, should skip
    processed2 = await worker.process_once()
    assert processed2 == 0

    # Verify no duplicate rows
    async with test_session_factory() as session:
        pricing_result = await session.execute(
            select(ProductPricing).where(ProductPricing.product_id == product_id)
        )
        pricings = list(pricing_result.scalars().all())
        assert len(pricings) == 1

        inv_result = await session.execute(
            select(ProductInventory).where(ProductInventory.product_id == product_id)
        )
        invs = list(inv_result.scalars().all())
        assert len(invs) == 1
