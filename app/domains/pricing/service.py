from uuid import UUID

from app.domains.pricing.repository import PricingRepository
from app.domains.pricing.events import PriceChanged
from app.core.outbox import OutboxStore
from app.core.uow import UnitOfWork


class PricingService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow
        self.outbox = OutboxStore(uow.session)
        self.repo = PricingRepository(uow.session)

    async def initialize(self, product_id: UUID, tenant_id: UUID, price: str,
                         compare_at_price: str | None = None, cost_price: str | None = None):
        await self.repo.create(
            product_id=product_id,
            tenant_id=tenant_id,
            price=price,
            compare_at_price=compare_at_price,
            cost_price=cost_price,
        )

    async def update_price(self, product_id: UUID, tenant_id: UUID, new_price: str):
        pricing = await self.repo.find_one(product_id=product_id, tenant_id=tenant_id)
        if not pricing:
            return
        old_price = str(pricing.price)
        await self.repo.update(pricing, price=new_price)
        await self.outbox.append(PriceChanged(
            product_id=product_id,
            tenant_id=tenant_id,
            old_price=old_price,
            new_price=new_price,
        ))

    async def get(self, product_id: UUID, tenant_id: UUID):
        return await self.repo.find_one(product_id=product_id, tenant_id=tenant_id)

    @staticmethod
    async def get_snapshot(session, product_id: UUID, tenant_id: UUID) -> dict | None:
        from app.domains.pricing.models import ProductPricing
        from sqlalchemy import select
        result = await session.execute(
            select(ProductPricing).where(
                ProductPricing.product_id == product_id,
                ProductPricing.tenant_id == tenant_id,
            )
        )
        pricing = result.scalar_one_or_none()
        if not pricing:
            return None
        return {
            "price": str(pricing.price),
            "compare_at_price": str(pricing.compare_at_price) if pricing.compare_at_price else None,
            "cost_price": str(pricing.cost_price) if pricing.cost_price else None,
        }


async def handle_product_created(event_data: dict, session_factory):
    tenant_id = UUID(event_data["tenant_id"]) if isinstance(event_data["tenant_id"], str) else event_data["tenant_id"]
    product_id = UUID(event_data["product_id"]) if isinstance(event_data["product_id"], str) else event_data["product_id"]
    async with UnitOfWork(tenant_id=str(tenant_id), session_factory=session_factory) as uow:
        svc = PricingService(uow)
        await svc.initialize(
            product_id=product_id,
            tenant_id=tenant_id,
            price=event_data.get("price", "0.00"),
            compare_at_price=event_data.get("compare_at_price"),
        )
        await uow.commit()
