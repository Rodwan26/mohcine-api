from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.core.deps import get_uow
from app.api.deps import require_auth, AuthContext
from app.core.uow import UnitOfWork
from app.domains.pricing.models import ProductPricing
from app.domains.inventory.models import ProductInventory
from app.models.tenant import Tenant
from app.models.user import User


@pytest_asyncio.fixture
async def user(db_session, tenant_id):
    uid = uuid4()
    u = User(id=uid, tenant_id=tenant_id, email=f"u-{uid}@test.com", password_hash="x", name="Tester")
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def order_setup(uow, tenant_id, product):
    pid = product.id
    uow.session.add(ProductPricing(
        product_id=pid, tenant_id=tenant_id, price=Decimal("29.99"),
    ))
    uow.session.add(ProductInventory(
        product_id=pid, tenant_id=tenant_id, sku="TST-001", quantity=100, reserved_quantity=0,
    ))
    await uow.commit()
    return {"product_id": pid, "tenant_id": tenant_id}


@pytest_asyncio.fixture
async def api_client(db_session, tenant_id, user, test_session_factory):
    async def _override_uow():
        async with UnitOfWork(
            tenant_id=str(tenant_id),
            session_factory=test_session_factory,
        ) as u:
            yield u

    ac = AuthContext(user=user, tenant_id=tenant_id)
    app.dependency_overrides[get_uow] = _override_uow
    app.dependency_overrides[require_auth] = lambda: ac

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


class TestOrderRoutes:
    async def test_create_order(self, api_client, order_setup):
        pid = str(order_setup["product_id"])
        resp = await api_client.post("/api/v1/orders", json={
            "items": [{"product_id": pid, "quantity": 2}],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "pending"
        assert data["subtotal"] == "59.98"
        assert data["total_amount"] == "59.98"
        assert len(data["items"]) == 1
        assert data["items"][0]["product_name"] == f"p-{order_setup['product_id']}"
        assert data["items"][0]["quantity"] == 2

    async def test_get_order(self, api_client, order_setup):
        pid = str(order_setup["product_id"])
        create_resp = await api_client.post("/api/v1/orders", json={
            "items": [{"product_id": pid, "quantity": 1}],
        })
        order_id = create_resp.json()["id"]

        get_resp = await api_client.get(f"/api/v1/orders/{order_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == order_id

    async def test_list_orders(self, api_client, order_setup):
        pid = str(order_setup["product_id"])
        await api_client.post("/api/v1/orders", json={
            "items": [{"product_id": pid, "quantity": 1}],
        })

        list_resp = await api_client.get("/api/v1/orders")
        assert list_resp.status_code == 200
        data = list_resp.json()
        assert len(data["items"]) >= 1

    async def test_cancel_order(self, api_client, order_setup):
        pid = str(order_setup["product_id"])
        create_resp = await api_client.post("/api/v1/orders", json={
            "items": [{"product_id": pid, "quantity": 1}],
        })
        order_id = create_resp.json()["id"]

        cancel_resp = await api_client.post(f"/api/v1/orders/{order_id}/cancel")
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "cancelled"

    async def test_confirm_order(self, api_client, order_setup):
        pid = str(order_setup["product_id"])
        create_resp = await api_client.post("/api/v1/orders", json={
            "items": [{"product_id": pid, "quantity": 1}],
        })
        order_id = create_resp.json()["id"]

        confirm_resp = await api_client.post(f"/api/v1/orders/{order_id}/confirm")
        assert confirm_resp.status_code == 200
        assert confirm_resp.json()["status"] == "confirmed"

    async def test_get_order_not_found(self, api_client):
        resp = await api_client.get(f"/api/v1/orders/{uuid4()}")
        assert resp.status_code == 404

    async def test_cancel_nonexistent_order(self, api_client):
        resp = await api_client.post(f"/api/v1/orders/{uuid4()}/cancel")
        assert resp.status_code == 404

    async def test_confirm_nonexistent_order(self, api_client):
        resp = await api_client.post(f"/api/v1/orders/{uuid4()}/confirm")
        assert resp.status_code == 404

    async def test_create_order_invalid_quantity(self, api_client, order_setup):
        pid = str(order_setup["product_id"])
        resp = await api_client.post("/api/v1/orders", json={
            "items": [{"product_id": pid, "quantity": 0}],
        })
        assert resp.status_code == 422

    async def test_create_order_empty_items(self, api_client):
        resp = await api_client.post("/api/v1/orders", json={"items": []})
        assert resp.status_code == 422

    async def test_cancel_already_cancelled_order(self, api_client, order_setup):
        pid = str(order_setup["product_id"])
        create_resp = await api_client.post("/api/v1/orders", json={
            "items": [{"product_id": pid, "quantity": 1}],
        })
        order_id = create_resp.json()["id"]

        await api_client.post(f"/api/v1/orders/{order_id}/cancel")
        cancel2 = await api_client.post(f"/api/v1/orders/{order_id}/cancel")
        assert cancel2.status_code == 400

    async def test_create_order_idempotent_api(self, api_client, order_setup):
        pid = str(order_setup["product_id"])
        body = {"items": [{"product_id": pid, "quantity": 1}], "idempotency_key": "dup-001"}
        resp1 = await api_client.post("/api/v1/orders", json=body)
        assert resp1.status_code == 201
        order_id = resp1.json()["id"]

        resp2 = await api_client.post("/api/v1/orders", json=body)
        assert resp2.status_code == 201
        assert resp2.json()["id"] == order_id

    async def test_order_not_visible_across_tenants_api(
        self, api_client, db_session, test_session_factory, order_setup,
    ):
        pid = str(order_setup["product_id"])
        create_resp = await api_client.post("/api/v1/orders", json={
            "items": [{"product_id": pid, "quantity": 1}],
        })
        assert create_resp.status_code == 201
        order_id = create_resp.json()["id"]

        other_tenant = uuid4()
        t = Tenant(id=other_tenant, name="Other Tenant", slug=f"other-{uuid4().hex[:8]}")
        db_session.add(t)
        uid = uuid4()
        other_user = User(id=uid, tenant_id=other_tenant, email=f"u-{uid}@test.com", password_hash="x", name="Other")
        db_session.add(other_user)
        await db_session.commit()

        async def _override_uow_b():
            async with UnitOfWork(
                tenant_id=str(other_tenant),
                session_factory=test_session_factory,
            ) as u:
                yield u

        app.dependency_overrides[get_uow] = _override_uow_b
        app.dependency_overrides[require_auth] = lambda: AuthContext(user=other_user, tenant_id=other_tenant)

        get_resp = await api_client.get(f"/api/v1/orders/{order_id}")
        assert get_resp.status_code == 404
