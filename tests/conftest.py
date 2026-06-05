from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.base import Base
from app.core.uow import UnitOfWork
from app.models.tenant import Tenant
from app.models.user import User
from app.models.event_outbox import EventOutbox
from app.domains.catalog.models import Product, Category, ProductVariant, Media
from app.domains.pricing.models import ProductPricing
from app.domains.inventory.models import ProductInventory, InventoryTransaction
from app.domains.orders.models import Order, OrderItem
from app.domains.payments.models import Payment

TEST_DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/mohcine_test"


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        yield session


@pytest_asyncio.fixture
async def tenant_id(db_session):
    t = Tenant(name="Test Tenant", slug="test-tenant")
    db_session.add(t)
    await db_session.commit()
    return t.id


# Session with tenant_id + user_id set in session.info
@pytest_asyncio.fixture
async def db_session_with_tenant(db_session, tenant_id):
    db_session.info["tenant_id"] = str(tenant_id)
    db_session.info["user_id"] = str(uuid4())
    return db_session


# UoW wrapping the prepared session
@pytest_asyncio.fixture
async def uow(db_session_with_tenant):
    tenant_id = db_session_with_tenant.info["tenant_id"]
    user_id = db_session_with_tenant.info["user_id"]
    uow = UnitOfWork(tenant_id=tenant_id, user_id=user_id)
    uow.session = db_session_with_tenant
    return uow


@pytest_asyncio.fixture
async def product(uow, tenant_id):
    pid = uuid4()
    p = Product(id=pid, tenant_id=tenant_id, name=f"p-{pid}",
                slug=f"p-{pid}", created_by=uuid4())
    uow.session.add(p)
    await uow.session.flush()
    return p


@pytest_asyncio.fixture
def test_session_factory(db_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    return async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
