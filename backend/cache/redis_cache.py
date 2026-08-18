"""Redis JSON cache. Read path: Redis -> DB -> populate Redis.
Refresh path: delete key -> run collectors -> store snapshot -> repopulate."""
import json
from typing import Any

import redis.asyncio as aioredis

from config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


def device_inventory_key(device_id: str) -> str:
    return f"rackinsight:device:{device_id}:inventory"


async def cache_get(key: str) -> Any | None:
    try:
        raw = await get_redis().get(key)
    except Exception as exc:  # Redis being down must never break reads
        logger.warning("Redis GET failed for key=%s: %s", key, exc)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def cache_set(key: str, value: Any, ttl_seconds: int | None = None) -> None:
    ttl = ttl_seconds if ttl_seconds is not None else get_settings().cache_ttl_seconds
    try:
        await get_redis().set(key, json.dumps(value, default=str), ex=ttl)
    except Exception as exc:
        logger.warning("Redis SET failed for key=%s: %s", key, exc)


async def cache_delete(key: str) -> None:
    try:
        await get_redis().delete(key)
    except Exception as exc:
        logger.warning("Redis DEL failed for key=%s: %s", key, exc)


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
