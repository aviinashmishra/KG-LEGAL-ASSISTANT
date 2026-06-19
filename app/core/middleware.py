"""ASGI middleware: request-id, timing, security headers, rate limiting, errors."""
from __future__ import annotations

import time
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings
from app.core.logging import get_logger
from app.core.ratelimit import get_limiter

logger = get_logger("kg-legal.http")

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-XSS-Protection": "1; mode=block",
}


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:  # global safety net
            logger.exception("unhandled error", extra={"request_id": request_id, "path": request.url.path})
            return JSONResponse(status_code=500, content={"detail": "Internal server error", "request_id": request_id})
        latency_ms = int((time.perf_counter() - start) * 1000)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-ms"] = str(latency_ms)
        for k, v in _SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method,
                "status_code": response.status_code,
                "latency_ms": latency_ms,
            },
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # only throttle API calls, not static assets / health
        if request.url.path.startswith("/api/"):
            settings = get_settings()
            client = request.client.host if request.client else "unknown"
            key = request.headers.get("x-api-key") or request.headers.get("authorization") or client
            if not get_limiter().allow(key, settings.rate_limit_per_min):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Slow down and retry shortly."},
                )
        return await call_next(request)
