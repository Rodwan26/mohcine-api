from uuid import UUID

import pytest

from app.domains.pricing.service import PricingService, handle_product_created


class TestPricingService:
    async def test_initialize_pricing(self, uow, tenant_id, product):
        svc = PricingService(uow)
        await svc.initialize(
            product_id=product.id,
            tenant_id=tenant_id,
            price="29.99",
            compare_at_price="39.99",
        )
        await uow.commit()
        result = await svc.get(product.id, tenant_id)
        assert result is not None
        assert str(result.price) == "29.99"
        assert str(result.compare_at_price) == "39.99"

    async def test_initialize_pricing_no_compare(self, uow, tenant_id, product):
        svc = PricingService(uow)
        await svc.initialize(product_id=product.id, tenant_id=tenant_id, price="10.00")
        await uow.commit()
        result = await svc.get(product.id, tenant_id)
        assert result is not None
        assert str(result.price) == "10.00"
        assert result.compare_at_price is None

    async def test_update_price(self, uow, tenant_id, product):
        svc = PricingService(uow)
        await svc.initialize(product_id=product.id, tenant_id=tenant_id, price="10.00")
        await uow.commit()
        await svc.update_price(product.id, tenant_id, "20.00")
        await uow.commit()
        result = await svc.get(product.id, tenant_id)
        assert str(result.price) == "20.00"

    async def test_get_nonexistent(self, uow, tenant_id):
        svc = PricingService(uow)
        result = await svc.get(UUID("00000000-0000-0000-0000-000000000099"), tenant_id)
        assert result is None

    async def test_update_price_nonexistent(self, uow, tenant_id):
        svc = PricingService(uow)
        await svc.update_price(
            UUID("00000000-0000-0000-0000-000000000098"),
            tenant_id,
            "50.00",
        )
        await uow.commit()
        result = await svc.get(UUID("00000000-0000-0000-0000-000000000098"), tenant_id)
        assert result is None


class TestPricingHandler:
    async def test_handle_product_created(self, tenant_id, test_session_factory):
        """handler creates pricing row via its own UoW."""
        from uuid import uuid4
        product_id = UUID("00000000-0000-0000-0000-000000000010")

        # Create product first (FK requirement) in test DB
        from app.domains.catalog.models import Product
        async with test_session_factory() as session:
            p = Product(id=product_id, tenant_id=tenant_id,
                        name="handler-pricing", slug="handler-pricing",
                        created_by=uuid4())
            session.add(p)
            await session.commit()

        await handle_product_created({
            "tenant_id": str(tenant_id),
            "product_id": str(product_id),
            "price": "15.50",
            "compare_at_price": None,
        }, test_session_factory)

        from app.domains.pricing.models import ProductPricing
        from sqlalchemy import select
        async with test_session_factory() as session:
            result = await session.execute(
                select(ProductPricing).where(ProductPricing.product_id == product_id)
            )
            pricing = result.scalar_one_or_none()
            assert pricing is not None
            assert str(pricing.price) == "15.50"
