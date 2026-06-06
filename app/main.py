import asyncio
import hashlib
import logging
import os
from contextlib import asynccontextmanager

from alembic.config import Config
from alembic import command
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1.router import api_v1_router
from app.core.database import engine, async_session_factory
from app.core.event_registry import EVENT_HANDLERS
from app.core.outbox import OutboxWorker
from app.middleware.tenant import TenantMiddleware

logger = logging.getLogger(__name__)

MIGRATION_LOCK_ID = int(hashlib.sha256(b"mohcine-api-migration").hexdigest()[:8], 16) & 0x7FFFFFFF

REQUIRED_TABLES = [
    "tenants",
    "users",
    "event_outbox",
    "products",
    "orders",
    "payments",
]

_worker: OutboxWorker | None = None


def _run_alembic_upgrade():
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")


async def run_migrations():
    if os.getenv("AUTO_MIGRATE", "true") != "true":
        return
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _run_alembic_upgrade)


async def verify_schema():
    async with engine.connect() as conn:
        for table in REQUIRED_TABLES:
            result = await conn.execute(
                text("SELECT to_regclass(:table)"),
                {"table": table},
            )
            if result.scalar() is None:
                raise RuntimeError(
                    f"schema missing required table: {table} — migrations failed or skipped"
                )


async def verify_bootstrap():
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT COUNT(*) FROM tenants"))
        count = result.scalar()
        if count == 0:
            logger.warning(
                "System not bootstrapped: no tenants found. "
                "POST /api/v1/system/bootstrap with X-Setup-Key to initialize."
            )


def start_outbox_worker():
    global _worker
    if os.getenv("ENABLE_OUTBOX", "true") != "true":
        return
    _worker = OutboxWorker(async_session_factory, EVENT_HANDLERS)
    asyncio.create_task(_worker.run_forever())


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.connect() as conn:
        await conn.execute(text(f"SELECT pg_advisory_lock({MIGRATION_LOCK_ID})"))
        await conn.commit()
        try:
            await run_migrations()
        finally:
            await conn.execute(text(f"SELECT pg_advisory_unlock({MIGRATION_LOCK_ID})"))
            await conn.commit()

    await verify_schema()
    await verify_bootstrap()
    start_outbox_worker()
    yield
    if _worker:
        await _worker.stop()


app = FastAPI(
    title="Mohcine API",
    description="SaaS e-commerce platform API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://mohcine-web.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)
app.add_middleware(TenantMiddleware)
app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
