from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Union

from .sanitizer import Sanitizer


MonitorReference = Union[str, Mapping[str, str]]
TRANSIENT_STATUSES = {408, 425, 429}


@dataclass(frozen=True)
class MonitorReceipt:
    accepted: bool = True
    incident_id: Optional[str] = None
    status: Optional[str] = None
    response: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HeartbeatOptions:
    status: str = "success"
    duration_ms: Optional[int] = None
    message: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: Optional[int] = None


@dataclass
class AssertionOptions:
    monitor: MonitorReference
    passed: bool
    kind: str = "wrong"
    expected: Any = None
    actual: Any = None
    duration_ms: Optional[int] = None
    message: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: Optional[int] = None


class MonitorRequestError(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = status_code is None or status_code in TRANSIENT_STATUSES or status_code >= 500


class MonitorClient:
    """Synchronous monitor transport with bounded evidence and safe retries."""

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        timeout: float = 5.0,
        retries: int = 2,
        sensitive_keys: Optional[list[str]] = None,
    ) -> None:
        self._api_key = api_key
        self._endpoint = endpoint
        self._timeout = timeout
        self._retries = max(0, min(retries, 5))
        self._sanitizer = Sanitizer(sensitive_keys)

    def heartbeat(self, url: str, options: Optional[HeartbeatOptions] = None) -> MonitorReceipt:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("oluso: heartbeat URL must be an absolute HTTPS URL")
        opts = options or HeartbeatOptions()
        payload = self._compact(
            {
                "status": opts.status,
                "duration_ms": opts.duration_ms,
                "message": opts.message,
                "evidence": self._sanitize(opts.context),
                "timestamp": opts.timestamp or int(time.time() * 1000),
            }
        )
        # Never attach the project signature to the secret heartbeat URL.
        return self._post(url, payload, authenticated=False)

    def assert_outcome(self, options: AssertionOptions) -> MonitorReceipt:
        payload = self._compact(
            {
                **self._reference(options.monitor),
                "kind": options.kind,
                "passed": options.passed,
                "expected": self._sanitize(options.expected),
                "actual": self._sanitize(options.actual),
                "duration_ms": options.duration_ms,
                "message": options.message,
                "context": self._sanitize(options.context),
                "timestamp": options.timestamp or int(time.time() * 1000),
            }
        )
        return self._post(self._endpoint, payload, authenticated=True)

    def workflow(
        self, monitor: MonitorReference, run_id: Optional[str] = None
    ) -> "MonitorWorkflow":
        return MonitorWorkflow(self, monitor, run_id or str(uuid.uuid4()))

    def workflow_event(
        self,
        monitor: MonitorReference,
        run_id: str,
        state: str,
        *,
        status: str = "running",
        duration_ms: Optional[int] = None,
        message: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        timestamp: Optional[int] = None,
    ) -> MonitorReceipt:
        if not run_id.strip() or not state.strip():
            raise ValueError("oluso: workflow run_id and state are required")
        payload = self._compact(
            {
                **self._reference(monitor),
                "kind": "workflow",
                "run_id": run_id,
                "state": state,
                "status": status,
                "duration_ms": duration_ms,
                "message": message,
                "context": self._sanitize(context or {}),
                "timestamp": timestamp or int(time.time() * 1000),
            }
        )
        return self._post(self._endpoint, payload, authenticated=True)

    def _post(self, url: str, payload: Dict[str, Any], authenticated: bool) -> MonitorReceipt:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if authenticated:
            headers["x-oluso-signature"] = self._api_key

        last_error: Optional[MonitorRequestError] = None
        for attempt in range(self._retries + 1):
            request = urllib.request.Request(url, data=body, method="POST", headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as response:
                    raw = response.read()
                    parsed = json.loads(raw) if raw else {}
                    if not isinstance(parsed, dict):
                        parsed = {}
                    return MonitorReceipt(
                        accepted=bool(parsed.get("accepted", True)),
                        incident_id=parsed.get("incident_id"),
                        status=parsed.get("status"),
                        response=parsed,
                    )
            except urllib.error.HTTPError as exc:
                last_error = MonitorRequestError(
                    f"oluso: monitor request failed with status {exc.code}", exc.code
                )
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = MonitorRequestError(f"oluso: monitor request failed: {exc}")

            if last_error is None or not last_error.retryable or attempt >= self._retries:
                break
            time.sleep(0.1 * (2**attempt))

        raise last_error or MonitorRequestError("oluso: monitor request failed")

    def _sanitize(self, value: Any) -> Any:
        return self._bound(self._sanitizer.sanitize_value(value, max_depth=8))

    def _bound(self, value: Any, depth: int = 0) -> Any:
        if depth >= 8:
            return "[Max Depth Reached]"
        if isinstance(value, str):
            return value[:4000] + ("... [truncated]" if len(value) > 4000 else "")
        if isinstance(value, dict):
            items = list(value.items())
            bounded = {str(k): self._bound(v, depth + 1) for k, v in items[:100]}
            if len(items) > 100:
                bounded["_truncated"] = True
            return bounded
        if isinstance(value, (list, tuple, set)):
            return [self._bound(v, depth + 1) for v in list(value)[:100]]
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return str(value)[:1000]

    @staticmethod
    def _reference(reference: MonitorReference) -> Dict[str, str]:
        if isinstance(reference, str):
            if not reference.strip():
                raise ValueError("oluso: monitor reference is required")
            return {"monitor": reference}
        monitor_id = reference.get("monitor_id")
        monitor = reference.get("monitor")
        if monitor_id:
            return {"monitor_id": monitor_id}
        if monitor:
            return {"monitor": monitor}
        raise ValueError("oluso: monitor reference needs monitor_id or monitor")

    @staticmethod
    def _compact(value: Dict[str, Any]) -> Dict[str, Any]:
        return {key: item for key, item in value.items() if item is not None}


class MonitorWorkflow:
    def __init__(self, client: MonitorClient, monitor: MonitorReference, run_id: str) -> None:
        self._client = client
        self._monitor = monitor
        self.run_id = run_id
        self._last_state: Optional[str] = None

    def checkpoint(self, state: str, **evidence: Any) -> MonitorReceipt:
        self._last_state = state
        return self._client.workflow_event(self._monitor, self.run_id, state, **evidence)

    def fail(self, state: str, **evidence: Any) -> MonitorReceipt:
        self._last_state = state
        return self._client.workflow_event(
            self._monitor, self.run_id, state, status="failed", **evidence
        )

    def complete(self, state: Optional[str] = None, **evidence: Any) -> MonitorReceipt:
        final_state = state or self._last_state
        if not final_state:
            raise ValueError("oluso: complete needs a state before the first checkpoint")
        self._last_state = final_state
        return self._client.workflow_event(
            self._monitor, self.run_id, final_state, status="completed", **evidence
        )
