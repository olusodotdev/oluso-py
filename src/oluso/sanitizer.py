from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Optional

DEFAULT_SENSITIVE_KEYS = [
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_token",
    "auth",
    "credentials",
    "mysql_pwd",
    "private_key",
    "privatekey",
    "session",
    "cookie",
    "csrf",
    "xsrf",
    "authorization",
    "bearer",
    "jwt",
    "ssn",
    "social_security",
    "credit_card",
    "card_number",
    "cvv",
    "pin",
]

REDACTED = "[REDACTED]"


class Sanitizer:
    """Redacts sensitive values from request data before it's reported."""

    def __init__(self, custom_sensitive_keys: Optional[Iterable[str]] = None) -> None:
        keys = list(DEFAULT_SENSITIVE_KEYS) + list(custom_sensitive_keys or [])
        self._patterns = [re.compile(re.escape(k), re.IGNORECASE) for k in keys]

    def _is_sensitive_key(self, key: str) -> bool:
        return any(p.search(key) for p in self._patterns)

    def sanitize_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for key, value in headers.items():
            lower = key.lower()
            if lower in ("authorization", "cookie") or self._is_sensitive_key(key):
                out[key] = REDACTED
            else:
                out[key] = str(value)
        return out

    def sanitize_query(self, query: Dict[str, Any]) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for key, value in query.items():
            if self._is_sensitive_key(key):
                out[key] = REDACTED
            elif isinstance(value, (list, tuple)):
                out[key] = ", ".join(str(v) for v in value)
            else:
                out[key] = str(value)
        return out

    def sanitize_value(self, value: Any, max_depth: int = 10) -> Any:
        """Recursively redact sensitive keys from arbitrary JSON-shaped data
        (dicts, lists, and primitives). Data of this shape can't contain
        cycles, so unlike sanitizing an arbitrary object graph, no
        circular-reference guard is needed.
        """
        return self._sanitize(value, max_depth)

    def _sanitize(self, value: Any, depth: int) -> Any:
        if depth <= 0:
            return "[Max Depth Reached]"

        if isinstance(value, dict):
            out: Dict[str, Any] = {}
            for key, val in value.items():
                if self._is_sensitive_key(str(key)):
                    out[key] = REDACTED
                else:
                    out[key] = self._sanitize(val, depth - 1)
            return out

        if isinstance(value, (list, tuple)):
            return [self._sanitize(item, depth - 1) for item in value]

        return value


def truncate_string(s: str, max_length: int = 1000) -> str:
    """Limit a string's length to prevent huge payloads."""
    if len(s) <= max_length:
        return s
    return s[:max_length] + "... [truncated]"
