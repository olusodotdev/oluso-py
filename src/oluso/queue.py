from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _QueuedReport:
    report: Dict[str, Any]
    timestamp: float
    retries: int = 0


class OfflineQueue:
    """Persists error reports that failed to send, for retry on the next
    successful send.
    """

    def __init__(self, max_size: int = 100, queue_dir: Optional[str] = None) -> None:
        self._max_size = max_size if max_size > 0 else 100
        directory = queue_dir or os.path.join(tempfile.gettempdir(), "oluso-queue")
        os.makedirs(directory, exist_ok=True)
        self._file_path = os.path.join(directory, "error-queue.json")

        self._lock = threading.Lock()
        self._queue: List[_QueuedReport] = []
        self._load()

    def enqueue(self, report: Dict[str, Any]) -> None:
        """report is an already-serialized report (see ErrorReport.to_dict())."""
        with self._lock:
            self._queue.append(_QueuedReport(report=report, timestamp=time.time()))
            if len(self._queue) > self._max_size:
                self._queue.pop(0)
            self._save()

    def size(self) -> int:
        with self._lock:
            return len(self._queue)

    def is_empty(self) -> bool:
        return self.size() == 0

    def clear(self) -> None:
        with self._lock:
            self._queue = []
            self._save()

    def _load(self) -> None:
        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return

        cutoff = time.time() - 24 * 60 * 60
        self._queue = [
            _QueuedReport(report=item["report"], timestamp=item["timestamp"], retries=item.get("retries", 0))
            for item in raw
            if item.get("timestamp", 0) > cutoff
        ]

    def _save(self) -> None:
        """Must be called with self._lock held."""
        try:
            payload = [
                {"report": q.report, "timestamp": q.timestamp, "retries": q.retries} for q in self._queue
            ]
            with open(self._file_path, "w", encoding="utf-8") as f:
                json.dump(payload, f)
        except OSError:
            pass

    def process_queue(self, send_fn: Callable[[dict], None]) -> None:
        """Attempt to send each queued report in order via send_fn (raises on
        failure), stopping at the first failure (which is requeued at the
        front with an incremented retry count, and dropped after 3 failed
        attempts).

        send_fn is called without holding the queue's lock, so enqueue() from
        another thread isn't blocked for the duration of a slow or hanging
        send.
        """
        while True:
            with self._lock:
                if not self._queue:
                    return
                item = self._queue[0]

            try:
                send_fn(item.report)
            except Exception:
                with self._lock:
                    if not self._queue or self._queue[0] is not item:
                        return  # queue mutated concurrently; bail out safely
                    item.retries += 1
                    if item.retries >= 3:
                        self._queue.pop(0)
                    self._save()
                return

            with self._lock:
                if not self._queue or self._queue[0] is not item:
                    return
                self._queue.pop(0)
                self._save()
