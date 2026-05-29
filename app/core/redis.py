from redis.asyncio import ConnectionPool, Redis

from app.core.config import settings

redis_pool = ConnectionPool.from_url(settings.REDIS_URL, decode_responses=True)


async def get_redis() -> Redis:
    return Redis(connection_pool=redis_pool)


async def ping_redis() -> bool:
    try:
        r = await get_redis()
        result = await r.ping()
        await r.aclose()
        return result
    except Exception:
        return False
