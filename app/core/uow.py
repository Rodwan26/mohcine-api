from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory


class UnitOfWork:
    def __init__(self, tenant_id: str | None = None, user_id: str | None = None,
                 session_factory=None):
        self.session: AsyncSession | None = None
        self._tenant_id = tenant_id
        self._user_id = user_id
        self._session_factory = session_factory or async_session_factory

    async def __aenter__(self):
        self.session = self._session_factory()
        if self._tenant_id:
            self.session.info["tenant_id"] = self._tenant_id
        if self._user_id:
            self.session.info["user_id"] = self._user_id
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            await self.rollback()
        await self.session.close()

    async def commit(self):
        await self.session.commit()

    async def rollback(self):
        await self.session.rollback()

    def set_tenant(self, tenant_id: str):
        if self.session:
            self.session.info["tenant_id"] = tenant_id

    def set_user(self, user_id: str):
        if self.session:
            self.session.info["user_id"] = user_id
