from __future__ import annotations

import logging
import queue
import threading
import time
import traceback
from typing import Any, Dict, Optional, Tuple

from .context import _snapshot
from .fingerprint import generate_fingerprint
from .options import Options
from .queue import OfflineQueue
from .rate_limiter import RateLimiter
from .sanitizer import Sanitizer
from .server_context import get_server_context
from .transport import TransportError, send_error_report
from .types import ErrorContext, ErrorReport, RequestContext, Severity

logger = logging.getLogger("oluso")


class Oluso:
    """Reports errors to Oluso.

    Sends run on a background daemon thread (tracked so `flush()` can drain
    them before shutdown) rather than blocking the calling thread on network
    I/O, since capture calls typically sit on a request-handling hot path.
    """

    def __init__(self, options: Options) -> None:
        if not options.api_key:
            raise ValueError("oluso: api_key is required")
        self._options = options
        self._sanitizer = Sanitizer(options.sensitive_keys)
        self._rate_limiter = RateLimiter(options.max_errors_per_minute)
        self._offline_queue = OfflineQueue(options.max_queue_size, options.queue_dir)

        self._send_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._pending = 0
        self._pending_lock = threading.Lock()
        self._all_sent = threading.Condition(self._pending_lock)
        self._worker = threading.Thread(target=self._worker_loop, name="oluso-sender", daemon=True)
        self._worker.start()

    @property
    def max_breadcrumbs(self) -> int:
        """The configured max breadcrumbs per scope, for framework
        integrations that open a scope themselves.
        """
        return self._options.max_breadcrumbs

    @property
    def sanitizer(self) -> Sanitizer:
        """The Sanitizer configured for this client (respects
        Options.sensitive_keys), for framework integrations that build a
        RequestContext manually.
        """
        return self._sanitizer

    def capture_exception(
        self, error: BaseException, custom_context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Report error, attaching any breadcrumbs/user/custom context on the
        current scope (see `oluso.scope`), plus any custom_context given
        here.
        """
        self._capture(error, http_info=None, custom_context=custom_context)

    def capture_http_error(
        self,
        error: BaseException,
        request_context: RequestContext,
        status_code: int,
        custom_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Like capture_exception but also attaches HTTP request context and
        a response status code, for reporting an error with request context
        from a framework integration.
        """
        self._capture(error, http_info=(request_context, status_code), custom_context=custom_context)

    def _capture(
        self,
        error: BaseException,
        http_info: Optional[Tuple[RequestContext, int]],
        custom_context: Optional[Dict[str, Any]],
    ) -> None:
        if error is None:
            return
        if self._options.should_report and not self._options.should_report(error):
            return
        if not self._rate_limiter.can_send():
            if self._options.log_to_console:
                logger.warning("[Oluso] rate limit exceeded, error not reported")
            return
        if self._options.log_to_console:
            logger.error("[Oluso] %s", error)

        stack_trace = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )
        err_ctx = self._build_error_context(http_info, custom_context)

        if self._options.fingerprint:
            fingerprint = self._options.fingerprint(error, err_ctx)
        else:
            fingerprint = generate_fingerprint(error, stack_trace)

        severity = self._options.default_severity
        if http_info is not None:
            _, status_code = http_info
            if status_code >= 500:
                severity = Severity.CRITICAL
            elif status_code >= 400:
                severity = Severity.HIGH

        report = ErrorReport(
            title=_error_title(error),
            message=str(error),
            stack_trace=stack_trace,
            environment=self._options.environment,
            severity=severity.value if isinstance(severity, Severity) else severity,
            tags=list(self._options.tags),
            fingerprint=fingerprint,
            context=err_ctx,
            timestamp=int(time.time() * 1000),
        )

        with self._pending_lock:
            self._pending += 1
        self._send_queue.put(report.to_dict())

    def _build_error_context(
        self,
        http_info: Optional[Tuple[RequestContext, int]],
        custom_context: Optional[Dict[str, Any]],
    ) -> ErrorContext:
        breadcrumbs, user, custom = _snapshot()

        if custom_context:
            custom = {**custom, **custom_context}

        err_ctx = ErrorContext(
            server=get_server_context(),
            user=user,
            custom=custom,
            breadcrumbs=breadcrumbs,
        )

        if http_info is not None:
            err_ctx.request = http_info[0]

        return err_ctx

    def _worker_loop(self) -> None:
        while True:
            report = self._send_queue.get()
            try:
                self._send_report(report)
            finally:
                with self._pending_lock:
                    self._pending -= 1
                    if self._pending <= 0:
                        self._all_sent.notify_all()
                self._send_queue.task_done()

    def _send_report(self, report: Dict[str, Any]) -> None:
        try:
            send_error_report(
                self._options.endpoint, report, self._options.api_key, self._options.timeout
            )
        except TransportError as e:
            if self._options.log_to_console:
                logger.error("[Oluso] failed to send error report: %s", e)
            if self._options.enable_offline_queue:
                self._offline_queue.enqueue(report)
            return

        if self._options.enable_offline_queue and not self._offline_queue.is_empty():
            self._offline_queue.process_queue(
                lambda r: send_error_report(
                    self._options.endpoint, r, self._options.api_key, self._options.timeout
                )
            )

    def flush(self, timeout: Optional[float] = None) -> bool:
        """Block until all in-flight and queued reports have been sent, or
        timeout elapses (None waits indefinitely). Returns True if everything
        was flushed before the timeout. Call this before your process exits
        so a capture right before shutdown isn't lost.
        """
        with self._pending_lock:
            deadline = None if timeout is None else time.time() + timeout
            while self._pending > 0:
                remaining = None if deadline is None else max(0.0, deadline - time.time())
                if remaining == 0.0:
                    return False
                if not self._all_sent.wait(remaining):
                    return False

        if self._options.enable_offline_queue and not self._offline_queue.is_empty():
            self._offline_queue.process_queue(
                lambda r: send_error_report(
                    self._options.endpoint, r, self._options.api_key, self._options.timeout
                )
            )
        return True


def _error_title(error: BaseException) -> str:
    message = str(error)
    first_line = message.splitlines()[0].strip() if message else ""
    if first_line:
        return first_line if len(first_line) <= 100 else first_line[:97] + "..."
    return f"{type(error).__name__} error"
