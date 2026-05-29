import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.core.database import engine, async_session_factory
from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.user import User
from sqlalchemy import select


async def seed():
    tenant_slug = os.getenv("SEED_TENANT_SLUG", "default")
    tenant_name = os.getenv("SEED_TENANT_NAME", "Default Store")
    admin_email = os.getenv("SEED_ADMIN_EMAIL", "admin@mohcine.com")
    admin_password = os.getenv("SEED_ADMIN_PASSWORD")
    admin_name = os.getenv("SEED_ADMIN_NAME", "Admin")

    if not admin_password:
        print("[seed] ERROR: SEED_ADMIN_PASSWORD is required")
        sys.exit(1)

    async with async_session_factory() as session:
        result = await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))
        tenant = result.scalar_one_or_none()

        if not tenant:
            tenant = Tenant(name=tenant_name, slug=tenant_slug)
            session.add(tenant)
            await session.commit()
            await session.refresh(tenant)
            print(f"[seed] Created tenant: {tenant_slug} ({tenant_name})")
        else:
            print(f"[seed] Tenant '{tenant_slug}' already exists — skipping")

        result = await session.execute(select(User).where(User.email == admin_email, User.tenant_id == tenant.id))
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                email=admin_email,
                password_hash=hash_password(admin_password),
                name=admin_name,
                tenant_id=tenant.id,
            )
            session.add(user)
            await session.commit()
            print(f"[seed] Created admin user: {admin_email}")
        else:
            print(f"[seed] Admin user '{admin_email}' already exists — skipping")

        print("[seed] Seed complete")
        if settings.DEBUG:
            print(f"[seed] (DEV) Tenant ID: {tenant.id}")
            print(f"[seed] (DEV) Admin email: {admin_email}")
            print(f"[seed] (DEV) Admin password: {admin_password}")
        else:
            print("[seed] Admin credentials are configured via environment variables")


if __name__ == "__main__":
    print("[seed] Starting seed script")
    asyncio.run(seed())
