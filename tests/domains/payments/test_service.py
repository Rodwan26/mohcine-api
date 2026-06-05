from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from app.domains.orders.service import OrderService
from app.domains.payments.models import Payment, PaymentStatus
from app.domains.payments.service import PaymentService, PaymentStateMachine
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
    pid = product.id
    uow.session.add(ProductPricing(
        product_id=pid, tenant_id=tenant_id, price=Decimal("29.99"),
    ))
    uow.session.add(ProductInventory(
        product_id=pid, tenant_id=tenant_id, sku="TST-001", quantity=100, reserved_quantity=0,
    ))
    return {"product_id": pid, "tenant_id": tenant_id}


@pytest_asyncio.fixture
async def order(uow, tenant_id, user_id, order_setup):
    svc = OrderService(uow)
    result = await svc.create_order(
        tenant_id=tenant_id,
        user_id=user_id,
        items_data=[{"product_id": order_setup["product_id"], "quantity": 1}],
    )
    return {"id": UUID(result["id"]), "tenant_id": tenant_id}


class TestPaymentStateMachine:
    def test_can_transition_valid(self):
        assert PaymentStateMachine.can_transition(PaymentStatus.PENDING, PaymentStatus.AUTHORIZED) is True
        assert PaymentStateMachine.can_transition(PaymentStatus.PENDING, PaymentStatus.PAID) is True
        assert PaymentStateMachine.can_transition(PaymentStatus.PENDING, PaymentStatus.FAILED) is True
        assert PaymentStateMachine.can_transition(PaymentStatus.PENDING, PaymentStatus.CANCELLED) is True
        assert PaymentStateMachine.can_transition(PaymentStatus.AUTHORIZED, PaymentStatus.PAID) is True
        assert PaymentStateMachine.can_transition(PaymentStatus.PAID, PaymentStatus.REFUNDED) is True

    def test_can_transition_invalid(self):
        assert PaymentStateMachine.can_transition(PaymentStatus.FAILED, PaymentStatus.PENDING) is False
        assert PaymentStateMachine.can_transition(PaymentStatus.REFUNDED, PaymentStatus.PENDING) is False
        assert PaymentStateMachine.can_transition(PaymentStatus.CANCELLED, PaymentStatus.PENDING) is False
        assert PaymentStateMachine.can_transition(PaymentStatus.PAID, PaymentStatus.AUTHORIZED) is False
        assert PaymentStateMachine.can_transition(PaymentStatus.PENDING, PaymentStatus.REFUNDED) is False

    def test_transition_same_status(self):
        assert PaymentStateMachine.can_transition(PaymentStatus.PENDING, PaymentStatus.PENDING) is False


class TestPaymentService:
    async def test_create_payment(self, uow, tenant_id, order):
        svc = PaymentService(uow)
        result = await svc.create_payment(
            tenant_id=tenant_id,
            order_id=order["id"],
            amount=Decimal("29.99"),
        )
        assert result is not None
        assert result["status"] == PaymentStatus.PENDING.value
        assert result["amount"] == "29.99"
        assert result["currency"] == "USD"

    async def test_create_payment_with_provider(self, uow, tenant_id, order):
        svc = PaymentService(uow)
        result = await svc.create_payment(
            tenant_id=tenant_id,
            order_id=order["id"],
            amount=Decimal("29.99"),
            provider="stripe",
            provider_reference="pi_123",
        )
        assert result["provider"] == "stripe"
        assert result["provider_reference"] == "pi_123"

    async def test_duplicate_payment_for_same_order(self, uow, tenant_id, order):
        svc = PaymentService(uow)
        await svc.create_payment(
            tenant_id=tenant_id,
            order_id=order["id"],
            amount=Decimal("29.99"),
        )
        with pytest.raises(ValueError, match="Order already has an active payment"):
            await svc.create_payment(
                tenant_id=tenant_id,
                order_id=order["id"],
                amount=Decimal("29.99"),
            )

    async def test_create_payment_idempotent(self, uow, tenant_id, order):
        svc = PaymentService(uow)
        r1 = await svc.create_payment(
            tenant_id=tenant_id,
            order_id=order["id"],
            amount=Decimal("29.99"),
            idempotency_key="pay-dup-001",
        )
        r2 = await svc.create_payment(
            tenant_id=tenant_id,
            order_id=order["id"],
            amount=Decimal("29.99"),
            idempotency_key="pay-dup-001",
        )
        assert r1["id"] == r2["id"]
        assert r2["status"] == PaymentStatus.PENDING.value

    async def test_confirm_payment(self, uow, tenant_id, order):
        svc = PaymentService(uow)
        created = await svc.create_payment(
            tenant_id=tenant_id,
            order_id=order["id"],
            amount=Decimal("29.99"),
        )
        result = await svc.confirm_payment(tenant_id, UUID(created["id"]))
        assert result["status"] == PaymentStatus.PAID.value

    async def test_fail_payment(self, uow, tenant_id, order):
        svc = PaymentService(uow)
        created = await svc.create_payment(
            tenant_id=tenant_id,
            order_id=order["id"],
            amount=Decimal("29.99"),
        )
        result = await svc.fail_payment(tenant_id, UUID(created["id"]), failure_reason="insufficient_funds")
        assert result["status"] == PaymentStatus.FAILED.value

    async def test_refund_payment(self, uow, tenant_id, order):
        svc = PaymentService(uow)
        created = await svc.create_payment(
            tenant_id=tenant_id,
            order_id=order["id"],
            amount=Decimal("29.99"),
        )
        await svc.confirm_payment(tenant_id, UUID(created["id"]))
        result = await svc.refund_payment(tenant_id, UUID(created["id"]))
        assert result["status"] == PaymentStatus.REFUNDED.value

    async def test_get_payment(self, uow, tenant_id, order):
        svc = PaymentService(uow)
        created = await svc.create_payment(
            tenant_id=tenant_id,
            order_id=order["id"],
            amount=Decimal("29.99"),
        )
        result = await svc.get_payment(tenant_id, UUID(created["id"]))
        assert result is not None
        assert result["id"] == created["id"]

    async def test_get_payment_not_found(self, uow, tenant_id):
        svc = PaymentService(uow)
        result = await svc.get_payment(tenant_id, uuid4())
        assert result is None

    async def test_confirm_nonexistent_payment(self, uow, tenant_id):
        svc = PaymentService(uow)
        result = await svc.confirm_payment(tenant_id, uuid4())
        assert result is None

    async def test_fail_nonexistent_payment(self, uow, tenant_id):
        svc = PaymentService(uow)
        result = await svc.fail_payment(tenant_id, uuid4())
        assert result is None

    async def test_refund_nonexistent_payment(self, uow, tenant_id):
        svc = PaymentService(uow)
        result = await svc.refund_payment(tenant_id, uuid4())
        assert result is None

    async def test_invalid_transition(self, uow, tenant_id, order):
        svc = PaymentService(uow)
        created = await svc.create_payment(
            tenant_id=tenant_id,
            order_id=order["id"],
            amount=Decimal("29.99"),
        )
        await svc.confirm_payment(tenant_id, UUID(created["id"]))
        with pytest.raises(ValueError, match="Cannot transition from paid to failed"):
            await svc.fail_payment(tenant_id, UUID(created["id"]))

    async def test_tenant_isolation(self, uow, tenant_id, order):
        other_tenant = uuid4()
        svc = PaymentService(uow)
        created = await svc.create_payment(
            tenant_id=tenant_id,
            order_id=order["id"],
            amount=Decimal("29.99"),
        )
        result_own = await svc.get_payment(tenant_id, UUID(created["id"]))
        assert result_own is not None
        result_other = await svc.get_payment(other_tenant, UUID(created["id"]))
        assert result_other is None
