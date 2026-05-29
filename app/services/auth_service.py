from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password, create_access_token
from app.models.user import User
from app.services.token_store import TokenStore
from app.core.exceptions import Conflict, Unauthorized, NotFound


class AuthService:
    def __init__(self, db: AsyncSession, token_store: TokenStore):
        self.db = db
        self.token_store = token_store

    async def register(self, email: str, password: str, name: str, tenant_id: str) -> User:
        result = await self.db.execute(select(User).where(User.email == email))
        existing = result.scalar_one_or_none()
        if existing:
            raise Conflict(message="Email already registered")

        user = User(
            email=email,
            password_hash=hash_password(password),
            name=name,
            tenant_id=tenant_id,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def login(self, email: str, password: str, tenant_id: str) -> dict:
        result = await self.db.execute(
            select(User).where(User.email == email, User.tenant_id == tenant_id)
        )
        user = result.scalar_one_or_none()

        if not user or not verify_password(password, user.password_hash):
            raise Unauthorized(message="Invalid email or password")

        if not user.is_active:
            raise Unauthorized(message="Account is disabled")

        access_token = create_access_token(
            data={"sub": str(user.id), "tenant_id": tenant_id, "email": user.email}
        )
        refresh_token = await self.token_store.save(str(user.id), tenant_id)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {"id": str(user.id), "email": user.email, "name": user.name},
        }

    async def refresh(self, refresh_token: str) -> dict:
        payload = await self.token_store.get(refresh_token)
        if not payload:
            raise Unauthorized(message="Invalid or expired refresh token")

        user_id = payload.get("user_id")
        tenant_id = payload.get("tenant_id")

        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise Unauthorized(message="User not found or disabled")

        access_token = create_access_token(
            data={"sub": str(user.id), "tenant_id": tenant_id, "email": user.email}
        )

        return {
            "access_token": access_token,
            "token_type": "bearer",
        }
