"""Request logging middleware for FastAPI."""

import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs every request's method, path, status code, and duration."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.exception(f"{request.method} {request.url.path} failed after {duration_ms:.1f}ms")
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(f"{request.method} {request.url.path} → {response.status_code} ({duration_ms:.1f}ms)")
        return response
