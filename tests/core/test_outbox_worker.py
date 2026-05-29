from uuid import uuid4
from unittest.mock import AsyncMock

import pytest

from app.core.outbox import OutboxWorker, OutboxStore
from app.core.events import DomainEvent, EventStatus
from app.models.event_outbox import EventOutbox
from sqlalchemy import select


@pytest.mark.asyncio
async def test_outbox_store_publishes_row(db_session):
    store = OutboxStore(db_session)

    @dataclass(frozen=True, kw_only=True)
    class DummyEvent(DomainEvent):
        product_id: str = "abc"
        quantity: int = 5

    await store.publish(DummyEvent(tenant_id=uuid4()))
    await db_session.flush()

    result = await db_session.execute(select(EventOutbox))
    rows = list(result.scalars().all())
    assert len(rows) == 1
    row = rows[0]
    assert row.event_name == "DummyEvent"
    assert row.status == EventStatus.PENDING
    payload = row.payload
    assert isinstance(payload, dict)
    assert payload["data"]["product_id"] == "abc"


@pytest.mark.asyncio
async def test_outbox_worker_processes_single_event(db_engine, db_session):
    """Worker picks up PENDING rows and dispatches to handler."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

    factory = async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)

    handler = AsyncMock()
    worker = OutboxWorker(session_factory=factory, handlers={
        "TestEvent": [handler],
    }, poll_interval=0.1)

    # Insert a row manually
    outbox = EventOutbox(
        event_name="TestEvent",
        payload={"data": {"msg": "hello"}},
        status=EventStatus.PENDING,
    )
    db_session.add(outbox)
    await db_session.commit()

    processed = await worker.process_once()
    assert processed == 1
    handler.assert_awaited_once_with({"msg": "hello"}, factory)


@pytest.mark.asyncio
async def test_outbox_worker_skips_completed(db_engine, db_session):
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

    factory = async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    handler = AsyncMock()
    worker = OutboxWorker(session_factory=factory, handlers={"TestEvent": [handler]})

    outbox = EventOutbox(
        event_name="TestEvent",
        payload={"data": {}},
        status=EventStatus.COMPLETED,
    )
    db_session.add(outbox)
    await db_session.commit()

    processed = await worker.process_once()
    assert processed == 0
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_outbox_worker_retry_on_failure(db_engine, db_session):
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

    factory = async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)

    fail_count = 0

    async def failing_handler(event_data, session_factory):
        nonlocal fail_count
        fail_count += 1
        msg = Exception("Handler failed")
        raise msg

    worker = OutboxWorker(
        session_factory=factory,
        handlers={"FailEvent": [failing_handler]},
        poll_interval=0.1,
        max_retries=3,
    )

    outbox = EventOutbox(
        event_name="FailEvent",
        payload={"data": {}},
        status=EventStatus.PENDING,
    )
    db_session.add(outbox)
    await db_session.commit()

    processed = await worker.process_once()
    assert processed == 0  # failed, so not counted as processed
    assert fail_count == 1

    # Reload from DB — worker modified row via a different session
    await db_session.refresh(outbox)
    assert outbox.status == EventStatus.PENDING  # retried, not failed yet
    assert outbox.retry_count == 1
    assert outbox.next_retry_at is not None
    assert "Handler failed" in (outbox.last_error or "")


@pytest.mark.asyncio
async def test_outbox_max_retries_reached(db_engine, db_session):
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

    factory = async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)

    async def always_fails(event_data, session_factory):
        msg = Exception("Always fails")
        raise msg

    worker = OutboxWorker(
        session_factory=factory,
        handlers={"FailForever": [always_fails]},
        max_retries=2,
    )

    outbox = EventOutbox(
        event_name="FailForever",
        payload={"data": {}},
        status=EventStatus.PENDING,
        retry_count=2,
    )
    db_session.add(outbox)
    await db_session.commit()

    processed = await worker.process_once()
    assert processed == 0

    await db_session.refresh(outbox)
    assert outbox.status == EventStatus.FAILED


@pytest.mark.asyncio
async def test_outbox_multiple_handlers(db_engine, db_session):
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

    factory = async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    handler1 = AsyncMock()
    handler2 = AsyncMock()
    worker = OutboxWorker(session_factory=factory, handlers={
        "MultiEvent": [handler1, handler2],
    })

    outbox = EventOutbox(
        event_name="MultiEvent",
        payload={"data": {"x": 1}},
        status=EventStatus.PENDING,
    )
    db_session.add(outbox)
    await db_session.commit()

    processed = await worker.process_once()
    assert processed == 1
    handler1.assert_awaited_once()
    handler2.assert_awaited_once()


from dataclasses import dataclass
