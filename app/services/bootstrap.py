from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.user import User


class BootstrapService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def status(self) -> dict:
        result = await self.db.execute(select(Tenant).limit(1))
        tenant = result.scalar_one_or_none()
        return {
            "bootstrapped": tenant is not None,
            "tenant_count": 1 if tenant else 0,
        }

    async def bootstrap(
        self,
        tenant_slug: str = "default",
        tenant_name: str = "Default Store",
        admin_email: str = "admin@mohcine.com",
        admin_password: str | None = None,
        admin_name: str = "Admin",
    ) -> dict:
        result = await self.db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
        tenant = result.scalar_one_or_none()

        created_tenant = False
        if not tenant:
            tenant = Tenant(name=tenant_name, slug=tenant_slug)
            self.db.add(tenant)
            await self.db.flush()
            created_tenant = True

        result = await self.db.execute(
            select(User).where(User.email == admin_email, User.tenant_id == tenant.id)
        )
        user = result.scalar_one_or_none()

        created_user = False
        if not user:
            user = User(
                email=admin_email,
                password_hash=hash_password(admin_password or str(uuid4())),
                name=admin_name,
                tenant_id=tenant.id,
            )
            self.db.add(user)
            await self.db.flush()
            created_user = True

        await self.db.commit()
        return {
            "bootstrapped": True,
            "tenant": {"slug": tenant_slug, "created": created_tenant},
            "admin": {"email": admin_email, "created": created_user},
        }
