from __future__ import annotations

import os
import platform
import threading
import time

from .types import ServerContext

_process_start = time.time()

try:
    import resource

    def _memory_rss_bytes() -> int:
        # ru_maxrss is KB on Linux, bytes on macOS/BSD.
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return rss * 1024 if platform.system() != "Darwin" else rss
except ImportError:  # resource is POSIX-only; not available on Windows

    def _memory_rss_bytes() -> int:
        return 0


def get_server_context() -> ServerContext:
    return ServerContext(
        hostname=platform.node(),
        platform=f"{platform.system()} {platform.release()}",
        python_version=platform.python_version(),
        process_id=os.getpid(),
        memory_rss=_memory_rss_bytes(),
        thread_count=threading.active_count(),
        uptime_seconds=time.time() - _process_start,
    )
