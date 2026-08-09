from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .types import FingerprintFunc, Severity, ShouldReportFunc

DEFAULT_ENDPOINT = "https://api.oluso.dev/api/v1/error/report"
DEFAULT_MONITOR_ENDPOINT = "https://api.oluso.dev/api/v1/monitors/events"


@dataclass
class Options:
    """Configures an :class:`~oluso.client.Oluso` client."""

    # API key for authentication (sent as the x-oluso-signature header). Required.
    api_key: str

    # Override the ingestion endpoint. Useful for self-hosting.
    endpoint: str = DEFAULT_ENDPOINT

    # Override the authenticated monitor event endpoint. Heartbeats use the
    # dedicated secret URL supplied by the Oluso dashboard instead.
    monitor_endpoint: str = DEFAULT_MONITOR_ENDPOINT
    monitor_retries: int = 2

    environment: str = "production"
    default_severity: Severity = Severity.MEDIUM
    tags: List[str] = field(default_factory=list)

    should_report: Optional[ShouldReportFunc] = None
    fingerprint: Optional[FingerprintFunc] = None

    # Timeout in seconds for each report request.
    timeout: float = 5.0

    log_to_console: bool = True

    max_breadcrumbs: int = 30

    enable_offline_queue: bool = True
    max_queue_size: int = 100
    # Override where the offline queue is persisted. Defaults to
    # <tempdir>/oluso-queue.
    queue_dir: Optional[str] = None

    max_errors_per_minute: int = 60
    sensitive_keys: List[str] = field(default_factory=list)
