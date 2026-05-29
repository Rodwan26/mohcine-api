from collections.abc import AsyncIterator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.uow import UnitOfWork


async def get_uow(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> AsyncIterator[UnitOfWork]:
    tenant_id = getattr(request.state, "tenant_id", None)
    user_id = getattr(request.state, "user_id", None)
    async with UnitOfWork(tenant_id=tenant_id, user_id=user_id) as uow:
        yield uow
