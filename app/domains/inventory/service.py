from uuid import UUID

from app.domains.inventory.repository import InventoryRepository, InvTxnRepository
from app.domains.inventory.events import StockChanged
from app.core.uow import UnitOfWork
from app.core.events import EventPublisher


class InventoryService:
    def __init__(self, uow: UnitOfWork, event_bus: EventPublisher | None = None):
        self.uow = uow
        self.event_bus = event_bus
        self.repo = InventoryRepository(uow.session)
        self.txn_repo = InvTxnRepository(uow.session)

    async def initialize(self, product_id: UUID, tenant_id: UUID, sku: str | None = None,
                         barcode: str | None = None, quantity: int = 0):
        await self.repo.create(
            product_id=product_id,
            tenant_id=tenant_id,
            sku=sku,
            barcode=barcode,
            quantity=quantity,
        )
        if quantity > 0:
            await self.txn_repo.create(
                tenant_id=tenant_id,
                product_id=product_id,
                type="purchase",
                quantity_change=quantity,
                running_balance=quantity,
                idempotency_key=f"init_{product_id}",
                note="Initial stock",
            )

    async def adjust_quantity(self, product_id: UUID, tenant_id: UUID, new_quantity: int):
        inv = await self.repo.find_one(product_id=product_id, tenant_id=tenant_id)
        if not inv:
            return
        old_qty = inv.quantity
        await self.repo.update(inv, quantity=new_quantity)
        diff = new_quantity - old_qty
        if diff != 0:
            await self.txn_repo.create(
                tenant_id=tenant_id,
                product_id=product_id,
                type="adjustment",
                quantity_change=diff,
                running_balance=new_quantity,
                idempotency_key=f"adj_{product_id}_{old_qty}_{new_quantity}",
                note="Manual adjustment",
            )
        if self.event_bus:
            await self.event_bus.publish(StockChanged(
                product_id=product_id,
                tenant_id=tenant_id,
                old_quantity=old_qty,
                new_quantity=new_quantity,
                reason="adjustment",
            ))

    async def reserve(self, product_id: UUID, tenant_id: UUID, quantity: int,
                      idempotency_key: str) -> bool:
        existing = await self.txn_repo.find_one(idempotency_key=idempotency_key)
        if existing:
            return True
        inv = await self.repo.find_one(product_id=product_id, tenant_id=tenant_id)
        if not inv:
            return False
        available = inv.quantity - inv.reserved_quantity
        if available < quantity:
            return False
        new_reserved = inv.reserved_quantity + quantity
        await self.repo.update(inv, reserved_quantity=new_reserved)
        await self.txn_repo.create(
            tenant_id=tenant_id,
            product_id=product_id,
            type="reservation",
            quantity_change=-quantity,
            running_balance=available - quantity,
            reference=idempotency_key,
            idempotency_key=idempotency_key,
        )
        return True

    async def commit_sale(self, product_id: UUID, tenant_id: UUID, quantity: int,
                          idempotency_key: str):
        existing = await self.txn_repo.find_one(idempotency_key=idempotency_key)
        if existing:
            return
        inv = await self.repo.find_one(product_id=product_id, tenant_id=tenant_id)
        if not inv:
            return
        new_qty = inv.quantity - quantity
        new_reserved = inv.reserved_quantity - quantity
        await self.repo.update(inv, quantity=new_qty, reserved_quantity=new_reserved)
        await self.txn_repo.create(
            tenant_id=tenant_id,
            product_id=product_id,
            type="sale",
            quantity_change=-quantity,
            running_balance=new_qty,
            reference=idempotency_key,
            idempotency_key=idempotency_key,
        )
        if self.event_bus:
            await self.event_bus.publish(StockChanged(
                product_id=product_id,
                tenant_id=tenant_id,
                old_quantity=inv.quantity,
                new_quantity=new_qty,
                reason="sale",
            ))

    async def release(self, product_id: UUID, tenant_id: UUID, quantity: int,
                      idempotency_key: str):
        existing = await self.txn_repo.find_one(idempotency_key=idempotency_key)
        if existing:
            return
        inv = await self.repo.find_one(product_id=product_id, tenant_id=tenant_id)
        if not inv:
            return
        new_reserved = max(0, inv.reserved_quantity - quantity)
        await self.repo.update(inv, reserved_quantity=new_reserved)
        await self.txn_repo.create(
            tenant_id=tenant_id,
            product_id=product_id,
            type="release",
            quantity_change=quantity,
            running_balance=inv.quantity - new_reserved,
            reference=idempotency_key,
            idempotency_key=idempotency_key,
        )

    async def get_available(self, product_id: UUID, tenant_id: UUID) -> int:
        inv = await self.repo.find_one(product_id=product_id, tenant_id=tenant_id)
        if not inv:
            return 0
        return inv.quantity - inv.reserved_quantity

    async def get(self, product_id: UUID, tenant_id: UUID):
        return await self.repo.find_one(product_id=product_id, tenant_id=tenant_id)


async def handle_product_created(event_data: dict, session_factory):
    tenant_id = UUID(event_data["tenant_id"]) if isinstance(event_data["tenant_id"], str) else event_data["tenant_id"]
    product_id = UUID(event_data["product_id"]) if isinstance(event_data["product_id"], str) else event_data["product_id"]
    async with UnitOfWork(tenant_id=str(tenant_id), session_factory=session_factory) as uow:
        svc = InventoryService(uow)
        await svc.initialize(
            product_id=product_id,
            tenant_id=tenant_id,
            sku=event_data.get("sku"),
            quantity=event_data.get("quantity", 0),
        )
        await uow.commit()
