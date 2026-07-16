from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable, Dict, List

import pytest


class RecordingServer:
    def __init__(self) -> None:
        self.requests: List[Dict[str, Any]] = []
        self.headers: List[Dict[str, str]] = []
        self._lock = threading.Lock()
        self.fail = False

        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 (stdlib naming convention)
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                try:
                    report = json.loads(body)
                except json.JSONDecodeError:
                    report = {}

                with server._lock:
                    server.requests.append(report)
                    server.headers.append({k.lower(): v for k, v in self.headers.items()})
                    should_fail = server.fail

                self.send_response(503 if should_fail else 200)
                self.end_headers()

            def log_message(self, format: str, *args: Any) -> None:  # silence stdout
                pass

        self._httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._httpd.server_port}"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def count(self) -> int:
        with self._lock:
            return len(self.requests)

    def last(self) -> Dict[str, Any]:
        with self._lock:
            return self.requests[-1]

    def set_fail(self, fail: bool) -> None:
        with self._lock:
            self.fail = fail

    def shutdown(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


@pytest.fixture
def recording_server():
    server = RecordingServer()
    yield server
    server.shutdown()


def wait_for(cond: Callable[[], bool], timeout: float = 2.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return
        time.sleep(0.01)
    raise AssertionError("condition not met before timeout")
