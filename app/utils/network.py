"""Lightweight network monitor.

Polls a tiny HTTPS endpoint periodically. Workers can pause until the network
comes back instead of burning retries when offline.
"""
from __future__ import annotations

import socket
import threading
import time
from typing import Callable, Optional


def is_online(host: str = "1.1.1.1", port: int = 443, timeout: float = 3.0) -> bool:
    """Fast TCP-level connectivity check; falls back to a DNS lookup."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        pass
    try:
        socket.gethostbyname("www.google.com")
        return True
    except OSError:
        return False


class NetworkMonitor:
    """Background thread that publishes online/offline transitions."""

    def __init__(
        self,
        interval: float = 5.0,
        on_change: Optional[Callable[[bool], None]] = None,
    ) -> None:
        self.interval = interval
        self._on_change = on_change
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._online = True
        self._lock = threading.Lock()
        self._online_event = threading.Event()
        self._online_event.set()

    @property
    def online(self) -> bool:
        with self._lock:
            return self._online

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="network-monitor", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def wait_online(self, timeout: Optional[float] = None) -> bool:
        return self._online_event.wait(timeout)

    def _set_state(self, online: bool) -> None:
        changed = False
        with self._lock:
            if online != self._online:
                self._online = online
                changed = True
        if online:
            self._online_event.set()
        else:
            self._online_event.clear()
        if changed and self._on_change:
            try:
                self._on_change(online)
            except Exception:  # pragma: no cover - callback safety
                pass

    def _run(self) -> None:
        # Initial probe immediately so callers don't have to wait.
        self._set_state(is_online())
        while not self._stop.is_set():
            time.sleep(self.interval)
            self._set_state(is_online())
