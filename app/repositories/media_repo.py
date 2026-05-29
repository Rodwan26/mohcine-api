from app.core.repository import TenantRepository
from app.models.media import Media


class MediaRepository(TenantRepository):
    def __init__(self, session):
        super().__init__(Media, session)

    async def find_by_entity(self, entity_type: str, entity_id: str) -> list:
        stmt = self.query().where(
            Media.entity_type == entity_type,
            Media.entity_id == entity_id,
        ).order_by(Media.sort_order)
        return await self.find_many(stmt)
