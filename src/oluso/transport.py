from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict


class TransportError(Exception):
    """Raised when a report fails to send. Carries no special data -- callers
    only need to know it failed, so it can be queued for retry.
    """


MAX_PAYLOAD_BYTES = 512 * 1024


def send_error_report(
    endpoint: str, report: Dict[str, Any], api_key: str, timeout: float
) -> None:
    """POST report to endpoint. Raises TransportError on any failure
    (network error, timeout, or non-2xx status) so callers can decide how to
    handle it (e.g. enqueue for retry) -- this never fails silently the way
    a fire-and-forget call would.
    """
    body = json.dumps(report).encode("utf-8")
    if len(body) > MAX_PAYLOAD_BYTES:
        raise TransportError(
            f"oluso: report payload is {len(body)} bytes; maximum is {MAX_PAYLOAD_BYTES}"
        )
    req = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-oluso-signature": api_key,
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            if status < 200 or status >= 300:
                raise TransportError(f"oluso: reporting failed with status {status}")
    except urllib.error.HTTPError as e:
        raise TransportError(f"oluso: reporting failed with status {e.code}") from e
    except urllib.error.URLError as e:
        raise TransportError(f"oluso: send report: {e.reason}") from e
    except TimeoutError as e:
        raise TransportError(f"oluso: send report timed out: {e}") from e
