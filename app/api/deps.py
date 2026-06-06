from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_tenant
from app.core.security import decode_access_token
from app.core.exceptions import Unauthorized, NotFound
from app.models.user import User


@dataclass
class AuthContext:
    user: User
    tenant_id: UUID


async def resolve_tenant_id(
    tenant_id: UUID = Depends(require_tenant),
) -> UUID:
    return tenant_id


async def get_current_tenant(request: Request) -> str:
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise NotFound(message="Tenant not found in request context")
    return tenant_id


async def get_current_user(
    request: Request,
    authorization: str = Header(alias="Authorization"),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization.startswith("Bearer "):
        raise Unauthorized(message="Invalid authorization header")

    token = authorization.removeprefix("Bearer ")
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise Unauthorized(message="Invalid or expired token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise Unauthorized(message="User not found or disabled")

    request.state.user_id = user_id
    return user


async def require_auth(
    user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant),
) -> AuthContext:
    return AuthContext(user=user, tenant_id=UUID(tenant_id))
