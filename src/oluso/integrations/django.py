"""Oluso integration for Django.

Django's middleware protocol calls `process_exception(request, exception)`
with the *real* exception before generating the error response -- unlike
Flask, this doesn't need a separate signal, it's built into the middleware
protocol itself. `__call__` still handles breadcrumb scoping for the whole
request and catching 5xx responses that aren't from a raised exception (e.g.
a view returning `HttpResponse(status=500)` directly).
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional

from ..client import Oluso
from ..context import _get_request_start_time, _set_request_start_time, add_breadcrumb, scope
from ..types import BreadcrumbLevel, RequestContext

_REPORTED_ATTR = "_oluso_reported"


class OlusoMiddleware:
    """Django middleware: scopes breadcrumbs to each request, auto-reports
    unhandled exceptions (via process_exception) and 5xx responses, then
    lets Django's own error handling continue -- this only observes and
    reports, it doesn't change how your app responds to errors.

    Configure by setting `OLUSO_CLIENT` in your Django settings to an
    `Oluso` instance::

        # settings.py
        from oluso import Oluso, Options
        OLUSO_CLIENT = Oluso(Options(api_key="your-api-key"))

        MIDDLEWARE = [
            "oluso.integrations.django.OlusoMiddleware",
            # ... your other middleware
        ]

    Django instantiates middleware with just `get_response`, so
    `OLUSO_CLIENT` in settings is how the client is normally supplied; an
    explicit `client` argument is also accepted for manual wiring (e.g. in
    tests).
    """

    def __init__(self, get_response: Callable, client: Optional[Oluso] = None) -> None:
        self.get_response = get_response
        self.client = client if client is not None else _resolve_client()

    def __call__(self, request: Any) -> Any:
        with scope(self.client.max_breadcrumbs):
            _set_request_start_time(time.time())
            method = getattr(request, "method", "")
            path = getattr(request, "path", "")

            add_breadcrumb(
                message=f"{method} {path}",
                level=BreadcrumbLevel.INFO,
                category="http",
                data={"method": method, "url": path},
            )

            response = self.get_response(request)

            status = getattr(response, "status_code", 200)
            if status >= 500 and not getattr(request, _REPORTED_ATTR, False):
                error = RuntimeError(f"server error: {status} - {method} {path}")
                content = getattr(response, "content", b"")
                setattr(error, "response", {
                    "status_code": status,
                    "headers": dict(getattr(response, "headers", {})),
                    "body": bytes(content[:4096]).decode("utf-8", "replace") if content else "",
                })
                self.client.capture_http_error(error, _build_request_context(self.client, request), status)

            add_breadcrumb(
                message=f"Response {status} - {method} {path}",
                level=BreadcrumbLevel.ERROR if status >= 400 else BreadcrumbLevel.INFO,
                category="http",
                data={"statusCode": status},
            )

            return response

    def process_exception(self, request: Any, exception: BaseException) -> None:
        setattr(request, _REPORTED_ATTR, True)
        req_ctx = _build_request_context(self.client, request)
        self.client.capture_http_error(exception, req_ctx, 500)
        return None  # let Django's own error handling generate the response


def _resolve_client() -> Oluso:
    from django.conf import settings

    client = getattr(settings, "OLUSO_CLIENT", None)
    if client is None:
        raise RuntimeError(
            "oluso: settings.OLUSO_CLIENT is not set. Add an Oluso instance to your "
            'Django settings, e.g.:\n\n    from oluso import Oluso, Options\n'
            '    OLUSO_CLIENT = Oluso(Options(api_key="your-api-key"))\n'
        )
    if not isinstance(client, Oluso):
        raise RuntimeError("oluso: settings.OLUSO_CLIENT must be an Oluso instance")
    return client


def _client_ip(request: Any) -> Optional[str]:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _build_request_context(client: Oluso, request: Any) -> RequestContext:
    headers: Dict[str, str] = {k: v for k, v in request.headers.items()}
    query: Dict[str, Any] = {k: v for k, v in request.GET.items()}

    response_time_ms: Optional[int] = None
    start = _get_request_start_time()
    if start is not None:
        response_time_ms = int((time.time() - start) * 1000)

    return RequestContext(
        url=request.path,
        method=request.method,
        headers=client.sanitizer.sanitize_headers(headers),
        query=client.sanitizer.sanitize_query(query),
        ip=_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT"),
        response_time_ms=response_time_ms,
    )
