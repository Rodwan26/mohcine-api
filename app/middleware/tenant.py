from fastapi import Request, HTTPException
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.database import async_session_factory
from app.models.tenant import Tenant

PUBLIC_ENDPOINTS = {
    "/health",
    "/live",
    "/ready",
    "/api/v1/health/live",
    "/api/v1/health/ready",
    "/api/v1/health/health",
    "/api/v1/ping",
    "/docs",
    "/redoc",
    "/openapi.json",
}


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if path in PUBLIC_ENDPOINTS:
            return await call_next(request)

        tenant_id = request.headers.get("X-Tenant-ID")
        if not tenant_id:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "MISSING_TENANT", "message": "X-Tenant-ID header is required", "details": {}}},
            )

        async with async_session_factory() as session:
            result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
            tenant = result.scalar_one_or_none()
            if not tenant:
                return JSONResponse(
                    status_code=404,
                    content={"error": {"code": "TENANT_NOT_FOUND", "message": f"Tenant {tenant_id} not found", "details": {}}},
                )

        request.state.tenant_id = tenant_id
        response = await call_next(request)
        return response
