from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.uow import UnitOfWork
from app.models.tenant import Tenant


async def require_tenant(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> UUID:
    slug: str | None = getattr(request.state, "tenant_slug", None)
    if not slug:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "MISSING_TENANT",
                    "message": "X-Tenant-ID header is required",
                    "details": {},
                }
            },
        )

    result = await session.execute(select(Tenant).where(Tenant.slug == slug))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "TENANT_NOT_FOUND",
                    "message": f"Tenant '{slug}' not found",
                    "details": {},
                }
            },
        )

    request.state.tenant_id = tenant.id
    return tenant.id


async def get_uow(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> AsyncIterator[UnitOfWork]:
    tenant_id = getattr(request.state, "tenant_id", None)
    user_id = getattr(request.state, "user_id", None)
    async with UnitOfWork(tenant_id=tenant_id, user_id=user_id) as uow:
        yield uow
