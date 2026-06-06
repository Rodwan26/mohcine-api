import asyncio
import hashlib
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1.router import api_v1_router
from app.core.database import engine, async_session_factory
from app.core.event_registry import EVENT_HANDLERS
from app.core.outbox import OutboxWorker
from app.middleware.tenant import TenantMiddleware

# deterministic 31-bit advisory lock ID derived from app name
LOCK_ID = int(hashlib.sha256(b"mohcine-api").hexdigest()[:8], 16) & 0x7FFFFFFF

REQUIRED_TABLES = [
    "tenants",
    "users",
    "event_outbox",
    "products",
    "orders",
    "payments",
]

_worker: OutboxWorker | None = None
_lock_conn = None


async def acquire_startup_lock():
    global _lock_conn
    _lock_conn = await engine.connect()
    await _lock_conn.execute(text(f"SELECT pg_advisory_lock({LOCK_ID})"))
    await _lock_conn.commit()


async def release_startup_lock():
    global _lock_conn
    if _lock_conn is not None:
        await _lock_conn.execute(text(f"SELECT pg_advisory_unlock({LOCK_ID})"))
        await _lock_conn.commit()
        await _lock_conn.close()
        _lock_conn = None


async def verify_schema():
    async with engine.connect() as conn:
        for table in REQUIRED_TABLES:
            result = await conn.execute(
                text("SELECT to_regclass(:table)"),
                {"table": table},
            )
            if result.scalar() is None:
                raise RuntimeError(
                    f"schema missing required table: {table} — run migrations first"
                )


def start_outbox_worker():
    global _worker
    if os.getenv("ENABLE_OUTBOX", "true") != "true":
        return
    _worker = OutboxWorker(async_session_factory, EVENT_HANDLERS)
    asyncio.create_task(_worker.run_forever())


@asynccontextmanager
async def lifespan(app: FastAPI):
    await acquire_startup_lock()
    await verify_schema()
    start_outbox_worker()
    yield
    if _worker:
        await _worker.stop()
    await release_startup_lock()


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
