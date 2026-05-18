"""
Request-ID middleware. Reads `X-Request-ID` if the caller already supplied one
(e.g. an upstream proxy / load balancer), otherwise mints a fresh short id.

The id is:
  1. Echoed back in the `X-Request-ID` response header.
  2. Bound to a contextvar so the JSON logger emits it on every line that fires
     during the request.
  3. Available via `request.state.request_id` for handlers that want to log
     contextually (e.g. job-creation paths so the SSE consumer correlates).
"""

from __future__ import annotations

import contextvars
import uuid
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Read by the logging filter. Empty string when there's no active request.
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "atlas_request_id", default=""
)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        rid = request.headers.get("x-request-id") or _short_id()
        token = request_id_ctx.set(rid)
        request.state.request_id = rid
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers["X-Request-ID"] = rid
        return response


def _short_id() -> str:
    return uuid.uuid4().hex[:12]
