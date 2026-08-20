import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.security import get_client_ip

_buckets: dict[str, deque[float]] = defaultdict(deque)
_redis_client = None


async def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    if not settings.redis_url:
        return None
    try:
        import redis.asyncio as redis

        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
        return _redis_client
    except Exception:
        return None


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


def _rate_limit_key(request: Request, scope: str) -> str:
    return f"{scope}:{get_client_ip(request)}"


def _default_limit(scope: str) -> int:
    limits = {
        "auth_login": settings.rate_limit_auth_per_minute,
        "auth_register": max(5, settings.rate_limit_auth_per_minute // 2),
        "forgot_password": settings.rate_limit_forgot_password_per_minute,
        "verify_email": 5,
        "invite": settings.rate_limit_invite_per_hour,
        "global_api": settings.rate_limit_global_per_minute,
    }
    return limits.get(scope, settings.rate_limit_auth_per_minute)


async def check_rate_limit(
    request: Request,
    scope: str,
    limit: int | None = None,
    window_seconds: int = 60,
) -> None:
    max_requests = limit or _default_limit(scope)
    key = _rate_limit_key(request, scope)
    now = time.time()
    window_start = now - window_seconds

    r = await _get_redis()
    if r:
        redis_key = f"rl:{key}:{window_seconds}"
        count = await r.incr(redis_key)
        if count == 1:
            await r.expire(redis_key, window_seconds)
        if count > max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Terlalu banyak percobaan. Coba lagi nanti.",
            )
        return

    bucket = _buckets[f"{key}:{window_seconds}"]
    while bucket and bucket[0] < window_start:
        bucket.popleft()

    if len(bucket) >= max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Terlalu banyak percobaan. Coba lagi nanti.",
        )

    bucket.append(now)
