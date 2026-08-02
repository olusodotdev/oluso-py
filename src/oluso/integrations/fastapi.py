"""Oluso integration for FastAPI (and any other ASGI application, since
this is plain ASGI middleware -- Starlette apps work identically).

Unlike the Flask and Django integrations, this one doesn't need a
framework-specific signal or hook to see the real exception from an
unhandled error. Starlette always wraps the whole app in its own
`ServerErrorMiddleware` (outermost), which is what actually converts an
unhandled exception into a 500 response; middleware added via
`app.add_middleware()` sits *inside* that layer, so a plain try/except
around calling the inner app sees the real exception before
ServerErrorMiddleware does.
"""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs

from ..client import Oluso
from ..context import _get_request_start_time, _set_request_start_time, add_breadcrumb
from ..context import scope as oluso_scope  # avoid clashing with the ASGI `scope` dict
from ..types import BreadcrumbLevel, RequestContext

Scope = Dict[str, Any]
Receive = Callable[[], Awaitable[Dict[str, Any]]]
Send = Callable[[Dict[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class OlusoMiddleware:
    """ASGI middleware: scopes breadcrumbs to each request, auto-reports
    unhandled exceptions and 5xx responses, then re-raises so Starlette's
    own error handling still runs -- this only observes and reports, it
    doesn't change how your app responds to errors.

    Usage::

        app.add_middleware(OlusoMiddleware, client=client)
    """

    def __init__(self, app: ASGIApp, client: Oluso) -> None:
        self.app = app
        self.client = client

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        with oluso_scope(self.client.max_breadcrumbs):
            _set_request_start_time(time.time())
            method = scope.get("method", "")
            path = scope.get("path", "")

            add_breadcrumb(
                message=f"{method} {path}",
                level=BreadcrumbLevel.INFO,
                category="http",
                data={"method": method, "url": path},
            )

            status_holder: Dict[str, Any] = {"body": bytearray(), "headers": {}}

            async def send_wrapper(message: Dict[str, Any]) -> None:
                if message["type"] == "http.response.start":
                    status_holder["code"] = message["status"]
                    status_holder["headers"] = {
                        k.decode("latin-1"): v.decode("latin-1")
                        for k, v in message.get("headers", [])
                    }
                elif message["type"] == "http.response.body" and len(status_holder["body"]) < 4096:
                    status_holder["body"].extend(message.get("body", b"")[:4096 - len(status_holder["body"])])
                await send(message)

            try:
                await self.app(scope, receive, send_wrapper)
            except Exception as exc:
                req_ctx = _build_request_context(self.client, scope)
                self.client.capture_http_error(exc, req_ctx, 500)
                raise

            status = status_holder.get("code", 200)
            if status >= 500:
                req_ctx = _build_request_context(self.client, scope)
                error = RuntimeError(f"server error: {status} - {method} {path}")
                setattr(error, "response", {
                    "status_code": status,
                    "headers": status_holder["headers"],
                    "body": bytes(status_holder["body"]).decode("utf-8", "replace"),
                })
                self.client.capture_http_error(error, req_ctx, status)

            add_breadcrumb(
                message=f"Response {status} - {method} {path}",
                level=BreadcrumbLevel.ERROR if status >= 400 else BreadcrumbLevel.INFO,
                category="http",
                data={"statusCode": status},
            )


def _build_request_context(client: Oluso, scope: Scope) -> RequestContext:
    raw_headers: List[Tuple[bytes, bytes]] = scope.get("headers", [])
    headers: Dict[str, str] = {
        name.decode("latin-1"): value.decode("latin-1") for name, value in raw_headers
    }

    query: Dict[str, Any] = {}
    query_string = scope.get("query_string", b"").decode("latin-1")
    if query_string:
        for key, values in parse_qs(query_string).items():
            query[key] = values[0] if len(values) == 1 else values

    client_info = scope.get("client")
    ip = client_info[0] if client_info else None

    response_time_ms: Optional[int] = None
    start = _get_request_start_time()
    if start is not None:
        response_time_ms = int((time.time() - start) * 1000)

    return RequestContext(
        url=scope.get("path", ""),
        method=scope.get("method", ""),
        headers=client.sanitizer.sanitize_headers(headers),
        query=client.sanitizer.sanitize_query(query),
        ip=ip,
        user_agent=headers.get("user-agent"),
        response_time_ms=response_time_ms,
    )
