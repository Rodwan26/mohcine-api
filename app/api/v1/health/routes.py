import time

import sqlalchemy as sa
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.redis import ping_redis

health_router = APIRouter(tags=["health"])


@health_router.get("/live")
async def live():
    return {"status": "alive"}


@health_router.get("/ready")
async def ready():
    db_ok = False
    redis_ok = False

    try:
        async with async_session_factory() as session:
            await session.execute(sa.text("SELECT 1"))
            db_ok = True
    except Exception:
        pass

    try:
        redis_ok = await ping_redis()
    except Exception:
        pass

    if db_ok and redis_ok:
        return {"status": "ready"}
    return {"status": "not ready"}


@health_router.get("/health")
async def health():
    db_status = "error"
    db_time = 0

    db_start = time.monotonic()
    try:
        async with async_session_factory() as session:
            await session.execute(sa.text("SELECT 1"))
            db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"
    db_time = round((time.monotonic() - db_start) * 1000)

    redis_status = "error"
    redis_time = 0
    redis_start = time.monotonic()
    try:
        result = await ping_redis()
        redis_status = "connected" if result else "error: ping failed"
    except Exception as e:
        redis_status = f"error: {str(e)}"
    redis_time = round((time.monotonic() - redis_start) * 1000)

    all_ok = db_status == "connected" and redis_status == "connected"
    overall = "ok" if all_ok else ("degraded" if db_status == "connected" or redis_status == "connected" else "down")

    return {
        "status": overall,
        "version": settings.APP_NAME,
        "checks": {
            "database": {"status": db_status, "response_time_ms": db_time},
            "redis": {"status": redis_status, "response_time_ms": redis_time},
        },
    }
