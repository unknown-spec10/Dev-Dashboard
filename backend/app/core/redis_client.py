import redis
from app.core.config import settings

_redis_client = None

def get_redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(settings.REDIS_URI, decode_responses=True)
    return _redis_client
