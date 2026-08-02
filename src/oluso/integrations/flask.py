"""Oluso integration for Flask (and any other WSGI application).

Two hooks are combined here, deliberately:

- A WSGI middleware wrapping the whole app, since that gives one
  synchronous call frame per request -- the natural place to open a single
  `oluso.scope()` context manager around it, and to catch 5xx responses that
  don't come from a raised exception (e.g. a view returning `"", 500`
  directly). As a side effect, this works for any WSGI app, not just Flask.
- Flask's `got_request_exception` signal, since Flask/Werkzeug catches an
  unhandled view exception *internally* and converts it to a 500 response
  before it would ever reach the outer WSGI middleware's `except` clause --
  without this signal, only a synthetic "server error: 500" message would
  be reported instead of the real exception.

Both paths mark the request as already-reported (via the WSGI environ, which
both share) so a raised exception is never double-reported.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs

from ..client import Oluso
from ..context import _get_request_start_time, _set_request_start_time, add_breadcrumb, scope
from ..types import BreadcrumbLevel, RequestContext

StartResponse = Callable[..., Any]
WSGIApp = Callable[[Dict[str, Any], StartResponse], Iterable[bytes]]

_REPORTED_KEY = "oluso.reported"


class OlusoMiddleware:
    """WSGI middleware: scopes breadcrumbs to each request and auto-reports
    5xx responses that aren't already covered by the `got_request_exception`
    signal (see module docstring). Lets exceptions propagate normally
    afterward -- this only observes and reports, it doesn't change how your
    app responds to errors.

    Note: status is captured from the synchronous `start_response` call, so
    a view that defers setting its status code until a streamed response
    body is iterated (uncommon in typical Flask apps) won't be captured
    accurately.
    """

    def __init__(self, wsgi_app: WSGIApp, client: Oluso) -> None:
        self.wsgi_app = wsgi_app
        self.client = client

    def __call__(self, environ: Dict[str, Any], start_response: StartResponse) -> Iterable[bytes]:
        with scope(self.client.max_breadcrumbs):
            _set_request_start_time(time.time())
            method = environ.get("REQUEST_METHOD", "")
            path = environ.get("PATH_INFO", "")

            add_breadcrumb(
                message=f"{method} {path}",
                level=BreadcrumbLevel.INFO,
                category="http",
                data={"method": method, "url": path},
            )

            status_holder: Dict[str, int] = {}

            def _start_response(status: str, headers: List[Tuple[str, str]], exc_info: Any = None) -> Any:
                status_holder["code"] = _parse_status_code(status)
                return start_response(status, headers, exc_info)

            try:
                result = self.wsgi_app(environ, _start_response)
            except Exception as exc:
                if not environ.get(_REPORTED_KEY):
                    req_ctx = _build_request_context(self.client, environ)
                    self.client.capture_http_error(exc, req_ctx, 500)
                raise

            status = status_holder.get("code", 200)
            if status >= 500 and not environ.get(_REPORTED_KEY):
                req_ctx = _build_request_context(self.client, environ)
                error = RuntimeError(f"server error: {status} - {method} {path}")
                if isinstance(result, (list, tuple)):
                    preview = b"".join(result)[:4096].decode("utf-8", "replace")
                    setattr(error, "response", {"status_code": status, "body": preview})
                self.client.capture_http_error(error, req_ctx, status)

            add_breadcrumb(
                message=f"Response {status} - {method} {path}",
                level=BreadcrumbLevel.ERROR if status >= 400 else BreadcrumbLevel.INFO,
                category="http",
                data={"statusCode": status},
            )

            return result


def init_app(app: Any, client: Oluso) -> None:
    """Register Oluso on a Flask app: `oluso.integrations.flask.init_app(app, client)`."""
    app.wsgi_app = OlusoMiddleware(app.wsgi_app, client)

    from flask import got_request_exception  # local import: flask is an optional dependency

    def _on_exception(sender: Any, exception: BaseException, **extra: Any) -> None:
        from flask import request

        request.environ[_REPORTED_KEY] = True
        req_ctx = _build_request_context(client, request.environ)
        client.capture_http_error(exception, req_ctx, 500)

    got_request_exception.connect(_on_exception, app, weak=False)


def _parse_status_code(status: str) -> int:
    try:
        return int(status.split(" ", 1)[0])
    except (ValueError, IndexError):
        return 200


def _build_request_context(client: Oluso, environ: Dict[str, Any]) -> RequestContext:
    method = environ.get("REQUEST_METHOD", "")
    path = environ.get("PATH_INFO", "")
    query_string = environ.get("QUERY_STRING", "")

    headers: Dict[str, str] = {}
    for key, value in environ.items():
        if key.startswith("HTTP_"):
            headers[key[5:].replace("_", "-").title()] = value
    if environ.get("CONTENT_TYPE"):
        headers["Content-Type"] = environ["CONTENT_TYPE"]
    if environ.get("CONTENT_LENGTH"):
        headers["Content-Length"] = environ["CONTENT_LENGTH"]

    query: Dict[str, Any] = {}
    if query_string:
        for key, values in parse_qs(query_string).items():
            query[key] = values[0] if len(values) == 1 else values

    response_time_ms: Optional[int] = None
    start = _get_request_start_time()
    if start is not None:
        response_time_ms = int((time.time() - start) * 1000)

    return RequestContext(
        url=path,
        method=method,
        headers=client.sanitizer.sanitize_headers(headers),
        query=client.sanitizer.sanitize_query(query),
        ip=environ.get("REMOTE_ADDR"),
        user_agent=environ.get("HTTP_USER_AGENT"),
        response_time_ms=response_time_ms,
    )
