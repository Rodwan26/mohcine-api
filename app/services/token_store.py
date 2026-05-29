import json
from uuid import uuid4

from redis.asyncio import Redis

from app.core.redis import redis_pool

REFRESH_PREFIX = "refresh_token:"
REFRESH_TTL = 7 * 24 * 60 * 60


class TokenStore:
    def __init__(self, redis: Redis | None = None):
        self._redis = redis

    async def _get_redis(self) -> Redis:
        if self._redis is None:
            return Redis(connection_pool=redis_pool)
        return self._redis

    async def save(self, user_id: str, tenant_id: str) -> str:
        jti = str(uuid4())
        key = f"{REFRESH_PREFIX}{jti}"
        payload = json.dumps({"user_id": user_id, "tenant_id": tenant_id})
        r = await self._get_redis()
        await r.setex(key, REFRESH_TTL, payload)
        return jti

    async def get(self, jti: str) -> dict | None:
        key = f"{REFRESH_PREFIX}{jti}"
        r = await self._get_redis()
        data = await r.get(key)
        if data is None:
            return None
        return json.loads(data)

    async def revoke(self, jti: str) -> None:
        key = f"{REFRESH_PREFIX}{jti}"
        r = await self._get_redis()
        await r.delete(key)

    async def revoke_all_for_user(self, user_id: str) -> None:
        r = await self._get_redis()
        async for key in r.scan_iter(match=f"{REFRESH_PREFIX}*"):
            data = await r.get(key)
            if data:
                payload = json.loads(data)
                if payload.get("user_id") == user_id:
                    await r.delete(key)
