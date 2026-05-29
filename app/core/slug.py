import re

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession


def _slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


async def generate_slug(
    name: str,
    model_cls: type,
    session: AsyncSession,
    tenant_id,
    exclude_id=None,
) -> str:
    base = _slugify(name)
    if not base:
        base = "item"

    stmt = select(func.count()).select_from(
        select(model_cls).where(
            model_cls.tenant_id == tenant_id,
            model_cls.slug.like(f"{base}%"),
        ).subquery()
    )
    result = await session.execute(stmt)
    count = result.scalar() or 0

    if count == 0:
        return base

    existing_stmt = select(model_cls.slug).where(
        model_cls.tenant_id == tenant_id,
        model_cls.slug.like(f"{base}%"),
    )
    existing_result = await session.execute(existing_stmt)
    existing = {row[0] for row in existing_result.fetchall()}

    candidate = base
    suffix = 2
    while candidate in existing:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate
