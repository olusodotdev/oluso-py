from __future__ import annotations

import hashlib
import re
from typing import Optional

_RE_NUMBER = re.compile(r"\d+")
_RE_UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)
_RE_PATH = re.compile(r"/[\w/.\-]+")
_RE_URL = re.compile(r"https?://\S+")
_RE_SPACE = re.compile(r"\s+")


def generate_fingerprint(error: BaseException, stack_trace: Optional[str] = None) -> str:
    """Produce a stable identifier for grouping similar errors together, from
    the error's type, a normalized version of its message (with dynamic
    values like IDs and paths stripped), and -- if provided -- a stack trace
    signature.
    """
    components = [type(error).__name__, _normalize_message(str(error))]
    if stack_trace:
        components.append(_stack_signature(stack_trace))

    digest = hashlib.sha256("|".join(components).encode("utf-8")).hexdigest()
    return digest[:8]


def _normalize_message(message: str) -> str:
    message = _RE_NUMBER.sub("N", message)
    message = _RE_UUID.sub("UUID", message)
    message = _RE_PATH.sub("PATH", message)
    message = _RE_URL.sub("URL", message)
    message = _RE_SPACE.sub(" ", message)
    return message.strip()


def _stack_signature(stack: str, limit: int = 6) -> str:
    """Extract just the call-site lines from a traceback (skipping the
    indented "File ..., line N" detail lines Python's traceback module
    produces), so the signature groups the same logical call site together
    even as line numbers shift.
    """
    frames = []
    for line in stack.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("File ") or stripped.startswith("Traceback"):
            continue
        frames.append(stripped)
        if len(frames) >= limit:
            break
    return "->".join(frames)
