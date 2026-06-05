from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.domains.orders.models import Order, OrderItem, OrderStatus
from app.domains.orders.service import OrderService, OrderStateMachine, handle_order_created
from app.domains.pricing.models import ProductPricing
from app.domains.inventory.models import ProductInventory
from app.models.user import User


@pytest.fixture
def user_id(db_session, tenant_id):
    uid = uuid4()
    u = User(id=uid, tenant_id=tenant_id, email=f"u-{uid}@test.com", password_hash="x", name="Tester")
    db_session.add(u)
    return uid


@pytest.fixture
def order_setup(uow, tenant_id, product):
    """Creates pricing + inventory for the product fixture."""
    pid = product.id
    uow.session.add(ProductPricing(
        product_id=pid, tenant_id=tenant_id, price=Decimal("29.99"),
    ))
    uow.session.add(ProductInventory(
        product_id=pid, tenant_id=tenant_id, sku="TST-001", quantity=100, reserved_quantity=0,
    ))
    return {"product_id": pid, "tenant_id": tenant_id}


class TestOrderService:
    async def test_create_order(self, uow, tenant_id, user_id, order_setup):
        svc = OrderService(uow)
        result = await svc.create_order(
            tenant_id=tenant_id,
            user_id=user_id,
            items_data=[{"product_id": order_setup["product_id"], "quantity": 2}],
        )
        assert result is not None
        assert result["status"] == OrderStatus.PENDING.value
        assert result["subtotal"] == "59.98"
        assert result["total_amount"] == "59.98"
        assert len(result["items"]) == 1
        assert result["items"][0]["product_name"] == f"p-{order_setup['product_id']}"
        assert result["items"][0]["unit_price"] == "29.99"
        assert result["items"][0]["quantity"] == 2
        assert result["items"][0]["sku"] == "TST-001"

    async def test_create_order_calculates_total(self, uow, tenant_id, user_id, order_setup):
        svc = OrderService(uow)
        result = await svc.create_order(
            tenant_id=tenant_id,
            user_id=user_id,
            items_data=[{"product_id": order_setup["product_id"], "quantity": 3}],
        )
        assert Decimal(result["subtotal"]) == Decimal("89.97")
        assert Decimal(result["total_amount"]) == Decimal(result["subtotal"])

    async def test_create_order_idempotent(self, uow, tenant_id, user_id, order_setup):
        svc = OrderService(uow)
        idem_key = "order-dup-001"
        r1 = await svc.create_order(
            tenant_id=tenant_id,
            user_id=user_id,
            items_data=[{"product_id": order_setup["product_id"], "quantity": 1}],
            idempotency_key=idem_key,
        )
        r2 = await svc.create_order(
            tenant_id=tenant_id,
            user_id=user_id,
            items_data=[{"product_id": order_setup["product_id"], "quantity": 1}],
            idempotency_key=idem_key,
        )
        assert r1["id"] == r2["id"]
        assert r2["status"] == OrderStatus.PENDING.value

    async def test_create_order_invalid_quantity(self, uow, tenant_id, user_id, order_setup):
        svc = OrderService(uow)
        with pytest.raises(ValueError, match="Quantity must be >= 1"):
            await svc.create_order(
                tenant_id=tenant_id,
                user_id=user_id,
                items_data=[{"product_id": order_setup["product_id"], "quantity": 0}],
            )

    async def test_create_order_no_items(self, uow, tenant_id, user_id):
        svc = OrderService(uow)
        with pytest.raises(ValueError, match="Order must have at least one item"):
            await svc.create_order(
                tenant_id=tenant_id,
                user_id=user_id,
                items_data=[],
            )

    async def test_create_order_nonexistent_product(self, uow, tenant_id, user_id):
        svc = OrderService(uow)
        result = await svc.create_order(
            tenant_id=tenant_id,
            user_id=user_id,
            items_data=[{"product_id": uuid4(), "quantity": 1}],
        )
        assert result is None

    async def test_get_order(self, uow, tenant_id, user_id, order_setup):
        svc = OrderService(uow)
        created = await svc.create_order(
            tenant_id=tenant_id,
            user_id=user_id,
            items_data=[{"product_id": order_setup["product_id"], "quantity": 1}],
        )
        result = await svc.get_order(tenant_id, UUID(created["id"]))
        assert result is not None
        assert result["id"] == created["id"]
        assert len(result["items"]) == 1

    async def test_get_order_not_found(self, uow, tenant_id):
        svc = OrderService(uow)
        result = await svc.get_order(tenant_id, uuid4())
        assert result is None

    async def test_confirm_order(self, uow, tenant_id, user_id, order_setup):
        svc = OrderService(uow)
        created = await svc.create_order(
            tenant_id=tenant_id,
            user_id=user_id,
            items_data=[{"product_id": order_setup["product_id"], "quantity": 1}],
        )
        result = await svc.confirm_order(tenant_id, UUID(created["id"]))
        assert result["status"] == OrderStatus.CONFIRMED.value

    async def test_cancel_order(self, uow, tenant_id, user_id, order_setup):
        svc = OrderService(uow)
        created = await svc.create_order(
            tenant_id=tenant_id,
            user_id=user_id,
            items_data=[{"product_id": order_setup["product_id"], "quantity": 1}],
        )
        result = await svc.cancel_order(tenant_id, UUID(created["id"]), reason="test")
        assert result["status"] == OrderStatus.CANCELLED.value

    async def test_confirm_nonexistent(self, uow, tenant_id):
        svc = OrderService(uow)
        result = await svc.confirm_order(tenant_id, uuid4())
        assert result is None

    async def test_transition_invalid(self, uow, tenant_id, user_id, order_setup):
        svc = OrderService(uow)
        created = await svc.create_order(
            tenant_id=tenant_id,
            user_id=user_id,
            items_data=[{"product_id": order_setup["product_id"], "quantity": 1}],
        )
        with pytest.raises(ValueError, match="Cannot transition from pending to shipped"):
            await svc.transition_status(tenant_id, UUID(created["id"]), OrderStatus.SHIPPED)

    async def test_transition_from_terminal(self, uow, tenant_id, user_id, order_setup):
        svc = OrderService(uow)
        created = await svc.create_order(
            tenant_id=tenant_id,
            user_id=user_id,
            items_data=[{"product_id": order_setup["product_id"], "quantity": 1}],
        )
        await svc.cancel_order(tenant_id, UUID(created["id"]))
        with pytest.raises(ValueError, match="Cannot transition from cancelled"):
            await svc.confirm_order(tenant_id, UUID(created["id"]))

    async def test_list_orders_empty(self, uow, tenant_id):
        svc = OrderService(uow)
        result = await svc.list_orders(tenant_id)
        assert result["items"] == []
        assert result["has_more"] is False

    async def test_list_orders_with_data(self, uow, tenant_id, user_id, order_setup):
        svc = OrderService(uow)
        for _ in range(3):
            await svc.create_order(
                tenant_id=tenant_id,
                user_id=user_id,
                items_data=[{"product_id": order_setup["product_id"], "quantity": 1}],
            )
        result = await svc.list_orders(tenant_id, limit=2)
        assert len(result["items"]) == 2
        assert result["has_more"] is True
        assert result["next_cursor"] is not None
        result2 = await svc.list_orders(tenant_id, cursor=result["next_cursor"], limit=2)
        assert len(result2["items"]) == 1
        assert result2["has_more"] is False

    async def test_tenant_isolation(self, uow, db_session, tenant_id, user_id, order_setup):
        other_tenant = uuid4()
        svc = OrderService(uow)
        await svc.create_order(
            tenant_id=tenant_id,
            user_id=user_id,
            items_data=[{"product_id": order_setup["product_id"], "quantity": 1}],
        )
        await uow.commit()
        result_own = await svc.list_orders(tenant_id)
        assert len(result_own["items"]) == 1
        result_other = await svc.list_orders(other_tenant)
        assert len(result_other["items"]) == 0


class TestOrderStateMachine:
    def test_can_transition_valid(self):
        assert OrderStateMachine.can_transition(OrderStatus.PENDING, OrderStatus.CONFIRMED) is True
        assert OrderStateMachine.can_transition(OrderStatus.CONFIRMED, OrderStatus.PROCESSING) is True
        assert OrderStateMachine.can_transition(OrderStatus.DELIVERED, OrderStatus.REFUNDED) is True

    def test_can_transition_invalid(self):
        assert OrderStateMachine.can_transition(OrderStatus.PENDING, OrderStatus.SHIPPED) is False
        assert OrderStateMachine.can_transition(OrderStatus.CANCELLED, OrderStatus.PENDING) is False
        assert OrderStateMachine.can_transition(OrderStatus.REFUNDED, OrderStatus.PENDING) is False

    def test_transition_same_status(self):
        assert OrderStateMachine.can_transition(OrderStatus.PENDING, OrderStatus.PENDING) is False


class TestOrderCreatedHandler:
    @pytest.fixture
    def handler_setup(self, uow, tenant_id, product):
        """Creates and COMMITS pricing + inventory for handler tests."""
        pid = product.id
        uow.session.add(ProductPricing(
            product_id=pid, tenant_id=tenant_id, price=Decimal("29.99"),
        ))
        uow.session.add(ProductInventory(
            product_id=pid, tenant_id=tenant_id, sku="TST-001", quantity=100, reserved_quantity=0,
        ))
        return {"product_id": pid, "tenant_id": tenant_id}

    async def test_handle_order_created_success(self, uow, tenant_id, user_id, handler_setup, test_session_factory):
        await uow.commit()
        svc = OrderService(uow)
        order = await svc.create_order(
            tenant_id=tenant_id,
            user_id=user_id,
            items_data=[{"product_id": handler_setup["product_id"], "quantity": 2}],
        )
        event_data = {
            "order_id": order["id"],
            "tenant_id": str(tenant_id),
            "items": [{"product_id": str(handler_setup["product_id"]), "quantity": 2}],
        }
        await handle_order_created(event_data, test_session_factory)

        result = await svc.get_order(tenant_id, UUID(order["id"]))
        assert result["status"] == OrderStatus.CONFIRMED.value

    async def test_handle_order_created_insufficient_stock(self, uow, tenant_id, user_id, handler_setup, test_session_factory):
        await uow.commit()
        svc = OrderService(uow)
        order = await svc.create_order(
            tenant_id=tenant_id,
            user_id=user_id,
            items_data=[{"product_id": handler_setup["product_id"], "quantity": 9999}],
        )
        event_data = {
            "order_id": order["id"],
            "tenant_id": str(tenant_id),
            "items": [{"product_id": str(handler_setup["product_id"]), "quantity": 9999}],
        }
        await handle_order_created(event_data, test_session_factory)

        result = await svc.get_order(tenant_id, UUID(order["id"]))
        assert result["status"] == OrderStatus.CANCELLED.value

    async def test_handle_order_created_idempotent(self, uow, tenant_id, user_id, handler_setup, test_session_factory):
        await uow.commit()
        svc = OrderService(uow)
        order = await svc.create_order(
            tenant_id=tenant_id,
            user_id=user_id,
            items_data=[{"product_id": handler_setup["product_id"], "quantity": 1}],
        )
        event_data = {
            "order_id": order["id"],
            "tenant_id": str(tenant_id),
            "items": [{"product_id": str(handler_setup["product_id"]), "quantity": 1}],
        }
        await handle_order_created(event_data, test_session_factory)
        await handle_order_created(event_data, test_session_factory)

        result = await svc.get_order(tenant_id, UUID(order["id"]))
        assert result["status"] == OrderStatus.CONFIRMED.value
