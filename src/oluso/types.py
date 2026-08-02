"""Data types for Oluso error reports.

These serialize to the same wire format the Node and Go SDKs use (camelCase
JSON keys, with the historical exception of ``stack_trace``), since all
Oluso SDKs report to the same backend API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class BreadcrumbLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


def _omit_none(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


@dataclass
class Breadcrumb:
    message: str
    level: BreadcrumbLevel = BreadcrumbLevel.INFO
    category: Optional[str] = None
    data: Optional[dict[str, Any]] = None
    timestamp: Optional[float] = None  # unix seconds, set when recorded

    def to_dict(self) -> dict[str, Any]:
        return _omit_none(
            {
                "timestamp": int(self.timestamp * 1000) if self.timestamp else None,
                "message": self.message,
                "level": self.level.value if isinstance(self.level, BreadcrumbLevel) else self.level,
                "category": self.category,
                "data": self.data,
            }
        )


@dataclass
class UserContext:
    id: Optional[str] = None
    email: Optional[str] = None
    username: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _omit_none(
            {
                "id": self.id,
                "email": self.email,
                "username": self.username,
                "extra": self.extra or None,
            }
        )


@dataclass
class RequestContext:
    url: str
    method: str
    headers: Optional[dict[str, str]] = None
    query: Optional[dict[str, str]] = None
    body: Any = None
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    response_time_ms: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return _omit_none(
            {
                "url": self.url,
                "method": self.method,
                "headers": self.headers,
                "query": self.query,
                "body": self.body,
                "ip": self.ip,
                "userAgent": self.user_agent,
                "responseTime": self.response_time_ms,
            }
        )


@dataclass
class ServerContext:
    hostname: str
    platform: str
    python_version: str
    process_id: int
    memory_rss: int
    thread_count: int
    uptime_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "hostname": self.hostname,
            "platform": self.platform,
            "pythonVersion": self.python_version,
            "processId": self.process_id,
            "memoryUsed": self.memory_rss,
            "threadCount": self.thread_count,
            "uptime": self.uptime_seconds,
        }


@dataclass
class ErrorContext:
    request: Optional[RequestContext] = None
    user: Optional[UserContext] = None
    server: Optional[ServerContext] = None
    custom: dict[str, Any] = field(default_factory=dict)
    breadcrumbs: list[Breadcrumb] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _omit_none(
            {
                "request": self.request.to_dict() if self.request else None,
                "user": self.user.to_dict() if self.user else None,
                "server": self.server.to_dict() if self.server else None,
                "custom": self.custom or None,
                "breadcrumbs": [b.to_dict() for b in self.breadcrumbs] or None,
            }
        )


@dataclass
class ErrorReport:
    title: str
    message: str
    stack_trace: Optional[str] = None
    environment: Optional[str] = None
    severity: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    fingerprint: Optional[str] = None
    context: Optional[ErrorContext] = None
    timestamp: Optional[int] = None  # unix millis
    schema_version: int = 2
    exception: Optional[dict[str, Any]] = None
    sdk: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return _omit_none(
            {
                "title": self.title,
                "message": self.message,
                "stack_trace": self.stack_trace,
                "environment": self.environment,
                "severity": self.severity,
                "tags": self.tags or None,
                "fingerprint": self.fingerprint,
                "context": self.context.to_dict() if self.context else None,
                "timestamp": self.timestamp,
                "schema_version": self.schema_version,
                "exception": self.exception,
                "sdk": self.sdk,
            }
        )


ShouldReportFunc = Callable[[BaseException], bool]
FingerprintFunc = Callable[[BaseException, Optional[ErrorContext]], str]
