from __future__ import annotations

import contextvars
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .types import Breadcrumb, BreadcrumbLevel, UserContext

_current_scope: "contextvars.ContextVar[Optional[_Scope]]" = contextvars.ContextVar(
    "oluso_scope", default=None
)


class _Scope:
    def __init__(self, max_breadcrumbs: int) -> None:
        self._lock = threading.Lock()
        self._max_breadcrumbs = max_breadcrumbs
        self.breadcrumbs: List[Breadcrumb] = []
        self.user: Optional[UserContext] = None
        self.custom: Dict[str, Any] = {}
        self.request_start: Optional[float] = None

    def add_breadcrumb(self, breadcrumb: Breadcrumb) -> None:
        with self._lock:
            breadcrumb.timestamp = time.time()
            self.breadcrumbs.append(breadcrumb)
            if len(self.breadcrumbs) > self._max_breadcrumbs:
                self.breadcrumbs.pop(0)

    def set_user(self, user: UserContext) -> None:
        with self._lock:
            self.user = user

    def set_custom(self, key: str, value: Any) -> None:
        with self._lock:
            self.custom[key] = value

    def snapshot(self) -> Tuple[List[Breadcrumb], Optional[UserContext], Dict[str, Any]]:
        with self._lock:
            return list(self.breadcrumbs), self.user, dict(self.custom)


@contextmanager
def scope(max_breadcrumbs: int = 30) -> Iterator[None]:
    """Context manager establishing an isolated breadcrumb/user/custom-data
    scope for the code inside it -- Python's equivalent of the per-request
    scope other Oluso SDKs build on Node's AsyncLocalStorage or Go's
    context.Context, implemented with contextvars instead, since that's the
    idiomatic mechanism for request/task-scoped state in Python (correctly
    isolated per thread AND per asyncio task).

    Framework integrations call this for you; call it yourself for
    non-request work (a background job, a CLI command) where you still want
    breadcrumbs/user context scoped to that one unit of work::

        with oluso.scope():
            oluso.add_breadcrumb("job started")
            client.capture_exception(err)
    """
    token = _current_scope.set(_Scope(max_breadcrumbs))
    try:
        yield
    finally:
        _current_scope.reset(token)


def add_breadcrumb(
    message: str,
    level: BreadcrumbLevel = BreadcrumbLevel.INFO,
    category: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    """Record a breadcrumb on the current scope. A no-op outside a scope()."""
    s = _current_scope.get()
    if s is None:
        return
    s.add_breadcrumb(Breadcrumb(message=message, level=level, category=category, data=data))


def set_user(user: UserContext) -> None:
    """Set the user context on the current scope. A no-op outside a scope()."""
    s = _current_scope.get()
    if s is not None:
        s.set_user(user)


def set_custom_context(key: str, value: Any) -> None:
    """Set a custom key/value on the current scope. A no-op outside a scope()."""
    s = _current_scope.get()
    if s is not None:
        s.set_custom(key, value)


def _set_request_start_time(t: float) -> None:
    s = _current_scope.get()
    if s is not None:
        s.request_start = t


def _get_request_start_time() -> Optional[float]:
    s = _current_scope.get()
    return s.request_start if s is not None else None


def _snapshot() -> Tuple[List[Breadcrumb], Optional[UserContext], Dict[str, Any]]:
    s = _current_scope.get()
    if s is None:
        return [], None, {}
    return s.snapshot()
