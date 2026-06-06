from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class TenantContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.tenant_slug = request.headers.get("X-Tenant-ID")
        return await call_next(request)
