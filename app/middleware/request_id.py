import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.middleware.rate_limit import check_rate_limit


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or __import__("uuid").uuid4().hex
        request.state.request_id = request_id
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class GlobalRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if os.getenv("TESTING", "").lower() not in ("1", "true", "yes"):
            if request.url.path.startswith("/api/") and request.url.path != "/api/health":
                await check_rate_limit(request, "global_api")
        return await call_next(request)
