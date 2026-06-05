import asyncio
import logging
import traceback
import warnings
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.events import DomainEvent, EventStatus, EventHandler
from app.models.event_outbox import EventOutbox

logger = logging.getLogger(__name__)


class OutboxStore:
    """Appends domain events to event_outbox table in the current UoW transaction.

    Does NOT call handlers. The OutboxWorker processes rows asynchronously.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def publish(self, event: DomainEvent) -> None:
        warnings.warn(
            "publish() is deprecated, use append() instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return await self.append(event)

    async def append(self, event: DomainEvent) -> None:
        raw = asdict(event)
        data = {}
        for k, v in raw.items():
            if isinstance(v, UUID):
                data[k] = str(v)
            elif isinstance(v, datetime):
                data[k] = v.isoformat()
            else:
                data[k] = v
        payload = {
            "event_name": event.event_name,
            "event_id": str(event.event_id),
            "occurred_at": event.occurred_at.isoformat(),
            "tenant_id": str(event.tenant_id) if event.tenant_id else None,
            "data": data,
        }
        self._session.add(EventOutbox(
            event_name=event.event_name,
            payload=payload,
            status=EventStatus.PENDING,
        ))


class OutboxWorker:
    """Background worker that polls event_outbox and dispatches to handlers.

    Usage:
        worker = OutboxWorker(session_factory, handlers)
        asyncio.create_task(worker.run_forever())

    Can also be run standalone:
        asyncio.run(worker.run_forever(poll_interval=1.0))
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        handlers: dict[str, list[Callable]] | None = None,
        poll_interval: float = 2.0,
        batch_size: int = 50,
        max_retries: int = 5,
    ):
        self._session_factory = session_factory
        self._handlers = handlers or {}
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._running = False

    async def start(self):
        self._running = True

    async def stop(self):
        self._running = False

    def _backoff_seconds(self, retry_count: int) -> float:
        return min(2 ** retry_count, 3600.0)

    async def process_once(self) -> int:
        processed = 0
        async with self._session_factory() as session:
            stmt = (
                select(EventOutbox)
                .where(
                    EventOutbox.status == EventStatus.PENDING,
                    (EventOutbox.next_retry_at.is_(None))
                    | (EventOutbox.next_retry_at <= datetime.now(timezone.utc)),
                )
                .order_by(EventOutbox.created_at)
                .limit(self._batch_size)
                .with_for_update(skip_locked=True)
            )
            result = await session.execute(stmt)
            rows = list(result.scalars().all())

            for row in rows:
                row.status = EventStatus.PROCESSING
                await session.flush()

                try:
                    handlers = self._handlers.get(row.event_name, [])
                    payload = row.payload if isinstance(row.payload, dict) else {}
                    event_data = payload.get("data", {})
                    for handler in handlers:
                        await handler(event_data, self._session_factory)
                    row.status = EventStatus.COMPLETED
                    row.processed_at = datetime.now(timezone.utc)
                    row.retry_count = 0
                    processed += 1
                except Exception as exc:
                    row.retry_count = (row.retry_count or 0) + 1
                    row.last_error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
                    if row.retry_count >= self._max_retries:
                        row.status = EventStatus.FAILED
                        logger.error(
                            "Outbox event %s failed after %d retries: %s",
                            row.event_name, row.retry_count, exc,
                        )
                    else:
                        row.status = EventStatus.PENDING
                        next_ts = datetime.now(timezone.utc).timestamp() + self._backoff_seconds(row.retry_count)
                        row.next_retry_at = datetime.fromtimestamp(next_ts, tz=timezone.utc)
                        logger.warning(
                            "Outbox event %s retry %d/%d: %s",
                            row.event_name, row.retry_count, self._max_retries, exc,
                        )

            await session.commit()
        return processed

    async def run_forever(self, poll_interval: float | None = None):
        self._running = True
        interval = poll_interval or self._poll_interval
        while self._running:
            try:
                processed = await self.process_once()
                if processed == 0:
                    await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("OutboxWorker error")
                await asyncio.sleep(interval)
