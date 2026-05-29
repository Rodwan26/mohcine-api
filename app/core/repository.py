import json
from datetime import datetime, timezone

from sqlalchemy import Select, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base import SoftDeleteMixin, AuditMixin, OptimisticLockMixin


def _make_cursor_value(row, sort_by: str = "created_at") -> str:
    ts = getattr(row, sort_by)
    id_val = str(row.id)
    return f"{ts.isoformat()}_{id_val}" if hasattr(ts, "isoformat") else id_val


class TenantRepository:
    def __init__(self, model, session: AsyncSession, current_user_id=None):
        self.model = model
        self.session = session
        self.tenant_id = session.info.get("tenant_id")
        self.current_user_id = current_user_id or session.info.get("user_id")

    def query(self) -> Select:
        stmt = select(self.model)
        if self.tenant_id:
            stmt = stmt.where(self.model.tenant_id == self.tenant_id)
        if getattr(self.model, "__soft_delete__", False):
            stmt = stmt.where(self.model.deleted_at.is_(None))
        return stmt

    async def find_one(self, **filters) -> object | None:
        stmt = self.query().filter_by(**filters)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_many(self, stmt: Select | None = None) -> list:
        if stmt is None:
            stmt = self.query()
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def paginate(self, stmt: Select | None = None, page: int = 1, per_page: int = 20) -> dict:
        if stmt is None:
            stmt = self.query()
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0
        offset = (page - 1) * per_page
        stmt = stmt.offset(offset).limit(per_page)
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
        }

    async def cursor_paginate(
        self,
        stmt: Select | None = None,
        cursor: str | None = None,
        limit: int = 20,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
    ) -> dict:
        if stmt is None:
            stmt = self.query()

        sort_col = getattr(self.model, sort_by)
        id_col = self.model.id

        order = sort_col.desc() if sort_dir == "desc" else sort_col.asc()
        order_id = id_col.desc() if sort_dir == "desc" else id_col.asc()

        if cursor:
            try:
                cursor_ts_str, cursor_id = cursor.rsplit("_", 1)
                cursor_ts = datetime.fromisoformat(cursor_ts_str)
            except (ValueError, AttributeError):
                cursor_ts = None
                cursor_id = cursor

            if cursor_ts is not None:
                if sort_dir == "desc":
                    stmt = stmt.where(
                        (sort_col < cursor_ts) | ((sort_col == cursor_ts) & (id_col < cursor_id))
                    )
                else:
                    stmt = stmt.where(
                        (sort_col > cursor_ts) | ((sort_col == cursor_ts) & (id_col > cursor_id))
                    )
            else:
                if sort_dir == "desc":
                    stmt = stmt.where(id_col < cursor_id)
                else:
                    stmt = stmt.where(id_col > cursor_id)

        stmt = stmt.order_by(order, order_id).limit(limit + 1)
        result = await self.session.execute(stmt)
        rows = list(result.scalars().all())

        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = _make_cursor_value(items[-1], sort_by) if items else None

        return {
            "items": items,
            "next_cursor": next_cursor if has_more else None,
            "has_more": has_more,
            "limit": limit,
        }

    async def create(self, **kwargs) -> object:
        if self.tenant_id and hasattr(self.model, "tenant_id"):
            kwargs.setdefault("tenant_id", self.tenant_id)
        if hasattr(self.model, "created_by") and self.current_user_id:
            kwargs.setdefault("created_by", self.current_user_id)
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def update(self, instance: object, **kwargs) -> object:
        if hasattr(self.model, "updated_by") and self.current_user_id:
            kwargs.setdefault("updated_by", self.current_user_id)
        for key, value in kwargs.items():
            setattr(instance, key, value)
        await self.session.flush()
        return instance

    async def soft_delete(self, instance: object) -> None:
        now = datetime.now(timezone.utc)
        setattr(instance, "deleted_at", now)
        setattr(instance, "is_active", False)
        if hasattr(self.model, "deleted_by") and self.current_user_id:
            setattr(instance, "deleted_by", self.current_user_id)
        await self.session.flush()
