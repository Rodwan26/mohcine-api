import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.database import async_session_factory
from app.core.event_registry import EVENT_HANDLERS
from app.core.outbox import OutboxWorker
from app.middleware.tenant import TenantMiddleware

app = FastAPI(
    title="Mohcine API",
    description="SaaS e-commerce platform API",
    version="0.1.0",
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

_worker: OutboxWorker | None = None


@app.on_event("startup")
async def startup():
    global _worker
    _worker = OutboxWorker(async_session_factory, EVENT_HANDLERS)
    asyncio.create_task(_worker.run_forever())


@app.on_event("shutdown")
async def shutdown():
    if _worker:
        await _worker.stop()


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
