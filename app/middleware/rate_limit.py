import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.security import get_client_ip

_buckets: dict[str, deque[float]] = defaultdict(deque)


def _rate_limit_key(request: Request, scope: str) -> str:
    return f"{scope}:{get_client_ip(request)}"


def check_rate_limit(request: Request, scope: str, limit: int | None = None) -> None:
    """Simple in-memory sliding window rate limiter for auth endpoints."""
    max_requests = limit or settings.rate_limit_auth_per_minute
    key = _rate_limit_key(request, scope)
    now = time.time()
    window_start = now - 60

    bucket = _buckets[key]
    while bucket and bucket[0] < window_start:
        bucket.popleft()

    if len(bucket) >= max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Terlalu banyak percobaan. Coba lagi nanti.",
        )

    bucket.append(now)
