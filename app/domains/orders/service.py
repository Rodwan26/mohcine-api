from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from app.core.outbox import OutboxStore
from app.core.uow import UnitOfWork
from app.domains.orders.models import Order, OrderItem, OrderStatus
from app.domains.orders.repository import OrderRepository, OrderItemRepository
from app.domains.orders.events import OrderCreated, OrderConfirmed, OrderCancelled, OrderStatusChanged


class OrderStateMachine:
    TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
        OrderStatus.PENDING: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED, OrderStatus.FAILED},
        OrderStatus.CONFIRMED: {OrderStatus.PROCESSING, OrderStatus.CANCELLED},
        OrderStatus.PROCESSING: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
        OrderStatus.SHIPPED: {OrderStatus.DELIVERED},
        OrderStatus.DELIVERED: {OrderStatus.REFUNDED},
        OrderStatus.CANCELLED: set(),
        OrderStatus.FAILED: set(),
        OrderStatus.REFUNDED: set(),
    }

    @staticmethod
    def can_transition(from_status: OrderStatus, to_status: OrderStatus) -> bool:
        return to_status in OrderStateMachine.TRANSITIONS.get(from_status, set())

    @staticmethod
    def transition(order: Order, to_status: OrderStatus) -> None:
        from_status = order.status
        if not OrderStateMachine.can_transition(from_status, to_status):
            raise ValueError(
                f"Cannot transition from {from_status.value} to {to_status.value}"
            )
        order.status = to_status


class OrderService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow
        self.outbox = OutboxStore(uow.session)
        self.repo = OrderRepository(uow.session)
        self.item_repo = OrderItemRepository(uow.session)

    async def create_order(
        self,
        tenant_id: UUID,
        user_id: UUID,
        items_data: list[dict],
        currency: str = "USD",
        notes: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict | None:
        if idempotency_key:
            existing = await self.repo.find_one(
                tenant_id=tenant_id, idempotency_key=idempotency_key
            )
            if existing:
                return self._order_to_response(existing)

        if not items_data:
            raise ValueError("Order must have at least one item")

        order_items = []
        subtotal = Decimal("0.00")
        for item in items_data:
            product_id = item["product_id"]
            quantity = item["quantity"]
            if not isinstance(product_id, UUID):
                product_id = UUID(product_id)
            if quantity < 1:
                raise ValueError(f"Quantity must be >= 1, got {quantity}")

            product_snap = await self._read_product_snapshot(product_id, tenant_id)
            if not product_snap or not product_snap.get("is_active"):
                return None

            pricing_snap = await self._read_pricing_snapshot(product_id, tenant_id)
            if not pricing_snap:
                return None

            inv_snap = await self._read_inventory_snapshot(product_id, tenant_id)

            unit_price = pricing_snap["price"]
            item_subtotal = _decimal_mul(unit_price, quantity)
            subtotal += item_subtotal

            order_items.append({
                "product_id": product_id,
                "product_name_snapshot": product_snap["name"],
                "sku_snapshot": inv_snap.get("sku") if inv_snap else None,
                "unit_price_snapshot": unit_price,
                "quantity": quantity,
                "subtotal": item_subtotal,
            })

        total_amount = subtotal

        order = await self.repo.create(
            tenant_id=tenant_id,
            user_id=user_id,
            status=OrderStatus.PENDING,
            currency=currency,
            subtotal=subtotal,
            total_amount=total_amount,
            notes=notes,
            idempotency_key=idempotency_key,
        )

        for oi in order_items:
            oi["tenant_id"] = tenant_id
            oi["order_id"] = order.id
            await self.item_repo.create(**oi)

        await self.outbox.append(OrderCreated(
            order_id=order.id,
            user_id=user_id,
            tenant_id=tenant_id,
            items=[
                {"product_id": str(i["product_id"]), "quantity": i["quantity"]}
                for i in order_items
            ],
            currency=currency,
            notes=notes,
        ))

        await self.uow.commit()

        return await self.get_order(tenant_id, order.id)

    async def confirm_order(self, tenant_id: UUID, order_id: UUID) -> dict | None:
        order = await self.repo.find_one(tenant_id=tenant_id, id=order_id)
        if not order:
            return None
        OrderStateMachine.transition(order, OrderStatus.CONFIRMED)
        await self.outbox.append(OrderConfirmed(
            order_id=order.id, tenant_id=tenant_id,
        ))
        await self.uow.commit()
        return await self.get_order(tenant_id, order_id)

    async def cancel_order(self, tenant_id: UUID, order_id: UUID, reason: str | None = None) -> dict | None:
        order = await self.repo.find_one(tenant_id=tenant_id, id=order_id)
        if not order:
            return None
        OrderStateMachine.transition(order, OrderStatus.CANCELLED)
        await self.outbox.append(OrderCancelled(
            order_id=order.id, tenant_id=tenant_id, reason=reason,
        ))
        await self.uow.commit()
        return await self.get_order(tenant_id, order_id)

    async def transition_status(self, tenant_id: UUID, order_id: UUID, new_status: OrderStatus) -> dict | None:
        order = await self.repo.find_one(tenant_id=tenant_id, id=order_id)
        if not order:
            return None
        old_status = order.status.value
        OrderStateMachine.transition(order, new_status)
        await self.outbox.append(OrderStatusChanged(
            order_id=order.id, tenant_id=tenant_id,
            old_status=old_status, new_status=new_status.value,
        ))
        await self.uow.commit()
        return await self.get_order(tenant_id, order_id)

    async def get_order(self, tenant_id: UUID, order_id: UUID) -> dict | None:
        order = await self.repo.find_one(tenant_id=tenant_id, id=order_id)
        if not order:
            return None
        items = await self.item_repo.find_many(
            select(OrderItem).where(
                OrderItem.order_id == order_id,
                OrderItem.tenant_id == tenant_id,
            )
        )
        return self._order_to_response(order, items)

    async def list_orders(
        self,
        tenant_id: UUID,
        status: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> dict:
        stmt = select(Order).where(Order.tenant_id == tenant_id)
        if status:
            stmt = stmt.where(Order.status == status)
        result = await self.repo.cursor_paginate(stmt, cursor=cursor, limit=limit)
        result["items"] = [self._order_to_response(o) for o in result["items"]]
        return result

    async def _read_product_snapshot(self, product_id: UUID, tenant_id: UUID) -> dict | None:
        from app.domains.catalog.service import CatalogService
        return await CatalogService.get_product_snapshot(self.uow.session, product_id, tenant_id)

    async def _read_pricing_snapshot(self, product_id: UUID, tenant_id: UUID) -> dict | None:
        from app.domains.pricing.service import PricingService
        return await PricingService.get_snapshot(self.uow.session, product_id, tenant_id)

    async def _read_inventory_snapshot(self, product_id: UUID, tenant_id: UUID) -> dict | None:
        from app.domains.inventory.service import InventoryService
        return await InventoryService.get_snapshot(self.uow.session, product_id, tenant_id)

    def _order_to_response(self, order: Order, items: list | None = None) -> dict:
        result = {
            "id": str(order.id),
            "user_id": str(order.user_id),
            "status": order.status.value if isinstance(order.status, OrderStatus) else order.status,
            "currency": order.currency,
            "subtotal": str(order.subtotal),
            "tax_amount": str(order.tax_amount) if order.tax_amount else None,
            "shipping_amount": str(order.shipping_amount) if order.shipping_amount else None,
            "discount_amount": str(order.discount_amount) if order.discount_amount else None,
            "total_amount": str(order.total_amount),
            "notes": order.notes,
            "idempotency_key": order.idempotency_key,
            "version_id": getattr(order, "version_id", 1),
            "created_at": order.created_at.isoformat(),
            "updated_at": order.updated_at.isoformat(),
        }
        if items is not None:
            result["items"] = [
                {
                    "id": str(i.id),
                    "product_id": str(i.product_id),
                    "product_name": i.product_name_snapshot,
                    "sku": i.sku_snapshot,
                    "unit_price": str(i.unit_price_snapshot),
                    "quantity": i.quantity,
                    "subtotal": str(i.subtotal),
                }
                for i in items
            ]
        return result


def _decimal_mul(price: str, quantity: int) -> Decimal:
    return Decimal(price) * quantity


async def handle_order_created(event_data: dict, session_factory):
    tenant_id = UUID(event_data["tenant_id"]) if isinstance(event_data["tenant_id"], str) else event_data["tenant_id"]
    order_id = UUID(event_data["order_id"]) if isinstance(event_data["order_id"], str) else event_data["order_id"]

    async with UnitOfWork(tenant_id=str(tenant_id), session_factory=session_factory) as uow:
        repo = OrderRepository(uow.session)
        order = await repo.find_one(id=order_id, tenant_id=tenant_id)
        if not order:
            await uow.commit()
            return
        await uow.session.refresh(order)

        if order.status != OrderStatus.PENDING:
            await uow.commit()
            return

        from app.domains.inventory.service import InventoryService
        inv_svc = InventoryService(uow)
        items = event_data.get("items", [])
        all_succeeded = True
        for item in items:
            pid = UUID(item["product_id"]) if isinstance(item["product_id"], str) else item["product_id"]
            qty = item["quantity"]
            idem_key = f"order_{order_id}_{item['product_id']}"
            ok = await inv_svc.reserve(
                product_id=pid,
                tenant_id=tenant_id,
                quantity=qty,
                idempotency_key=idem_key,
            )
            if not ok:
                all_succeeded = False
                break

        if all_succeeded:
            OrderStateMachine.transition(order, OrderStatus.CONFIRMED)
        else:
            OrderStateMachine.transition(order, OrderStatus.CANCELLED)

        await uow.commit()
