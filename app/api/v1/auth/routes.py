from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, resolve_tenant_id
from app.core.database import get_db
from app.models.user import User
from app.schemas.auth import RegisterRequest, LoginRequest, RefreshRequest
from app.services.auth_service import AuthService
from app.services.token_store import TokenStore

auth_router = APIRouter(tags=["auth"])


async def get_auth_service(db: AsyncSession = Depends(get_db)):
    token_store = TokenStore()
    return AuthService(db=db, token_store=token_store)


@auth_router.post("/register")
async def register(
    body: RegisterRequest,
    tenant_id: UUID = Depends(resolve_tenant_id),
    service: AuthService = Depends(get_auth_service),
):
    user = await service.register(
        email=body.email,
        password=body.password,
        name=body.name,
        tenant_id=str(tenant_id),
    )
    return {"data": {"user_id": str(user.id), "email": user.email}}


@auth_router.post("/login")
async def login(
    body: LoginRequest,
    tenant_id: UUID = Depends(resolve_tenant_id),
    service: AuthService = Depends(get_auth_service),
):
    result = await service.login(
        email=body.email,
        password=body.password,
        tenant_id=str(tenant_id),
    )
    return {"data": result}


@auth_router.post("/refresh")
async def refresh(
    body: RefreshRequest,
    service: AuthService = Depends(get_auth_service),
):
    result = await service.refresh(refresh_token=body.refresh_token)
    return {"data": result}


@auth_router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return {"data": {"id": str(user.id), "email": user.email, "name": user.name}}
