"""Single-item download worker.

A worker is a thread that:
  1. Pulls the next runnable item from the store
  2. Runs the yt-dlp downloader with retry / fallback
  3. Updates progress + status in the database
  4. Honors pause / cancel signals

Workers are intentionally stateless beyond their handles. The queue manager
spawns N of them and lets the SQLite store coordinate work.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from ..database import models as M
from ..database.store import QueueStore, parse_options
from ..downloader.ytdlp_runner import DownloadResult, ProgressEvent, YtdlpRunner
from ..settings.config import AppConfig
from ..utils.antibot import UserAgentPool, jitter_sleep
from ..utils.logging_setup import get_logger
from ..utils.network import NetworkMonitor

log = get_logger("download")
retry_log = get_logger("retry")


ProgressCallback = Callable[[int, ProgressEvent], None]
StatusCallback = Callable[[int, str, str], None]  # item_id, status, error


@dataclass
class WorkerHandles:
    """Mutable shared state between the queue manager and a worker."""

    stop_event: threading.Event
    pause_event: threading.Event  # set => paused
    network: NetworkMonitor
    progress_cb: Optional[ProgressCallback] = None
    status_cb: Optional[StatusCallback] = None
    poll_interval: float = 0.5


class DownloadWorker(threading.Thread):
    """A single download worker thread."""

    def __init__(
        self,
        name: str,
        store: QueueStore,
        config: AppConfig,
        ua_pool: UserAgentPool,
        handles: WorkerHandles,
    ) -> None:
        super().__init__(name=name, daemon=True)
        self.store = store
        self.config = config
        self.ua_pool = ua_pool
        self.handles = handles
        self._current_item_id: Optional[int] = None
        self._cancel_current = threading.Event()

    # ----- public control -----
    def cancel_current(self) -> None:
        self._cancel_current.set()

    @property
    def current_item_id(self) -> Optional[int]:
        return self._current_item_id

    # ----- main loop -----
    def run(self) -> None:  # noqa: D401
        log.info("%s started", self.name)
        while not self.handles.stop_event.is_set():
            if self.handles.pause_event.is_set():
                self._wait_unpaused()
                continue
            if not self.handles.network.online:
                self.handles.network.wait_online(timeout=5)
                continue
            item = self.store.next_runnable()
            if not item or item.id is None:
                time.sleep(self.handles.poll_interval)
                continue
            self._process(item)
        log.info("%s stopped", self.name)

    def _wait_unpaused(self) -> None:
        while self.handles.pause_event.is_set() and not self.handles.stop_event.is_set():
            time.sleep(0.2)

    # ----- per-item handling -----
    def _process(self, item: M.QueueItem) -> None:
        assert item.id is not None
        self._current_item_id = item.id
        self._cancel_current.clear()
        self._update_status(item.id, M.DOWNLOADING, "")

        jitter_sleep(self.config.request_delay_min_ms, self.config.request_delay_max_ms)

        result = self._download_with_retries(item)

        if result.ok:
            self.store.update(
                item.id,
                status=M.COMPLETED,
                progress=100.0,
                final_path=result.final_path,
                title=result.title or item.title,
                uploader=result.uploader or item.uploader,
                duration=result.duration or item.duration,
                upload_date=result.upload_date or item.upload_date,
                platform=result.platform or item.platform,
                error="",
                finished_at=time.time(),
            )
            log.info("[item %s] completed -> %s", item.id, result.final_path)
            if self.handles.status_cb:
                self.handles.status_cb(item.id, M.COMPLETED, "")
        else:
            err = result.error or "download failed"
            if err == "canceled":
                self.store.set_status(item.id, M.CANCELED, "")
                log.info("[item %s] canceled", item.id)
                if self.handles.status_cb:
                    self.handles.status_cb(item.id, M.CANCELED, "")
            elif self._is_skippable_error(err):
                self.store.set_status(item.id, M.SKIPPED, err)
                self.store.log_error(item.id, err, "SKIP")
                log.warning("[item %s] skipped: %s", item.id, err)
                if self.handles.status_cb:
                    self.handles.status_cb(item.id, M.SKIPPED, err)
            else:
                self.store.set_status(item.id, M.FAILED, err)
                self.store.log_error(item.id, err, "FAIL")
                log.error("[item %s] failed: %s", item.id, err)
                if self.handles.status_cb:
                    self.handles.status_cb(item.id, M.FAILED, err)
        self._current_item_id = None

    def _download_with_retries(self, item: M.QueueItem) -> DownloadResult:
        assert item.id is not None
        runner = YtdlpRunner(
            config=self.config,
            ua_pool=self.ua_pool,
            on_progress=lambda evt: self._on_progress(item.id, evt),  # type: ignore[arg-type]
            cancel_check=lambda: self._cancel_current.is_set() or self.handles.stop_event.is_set(),
            pause_check=lambda: self.handles.pause_event.is_set(),
        )
        overrides = parse_options(item)

        max_attempts = max(1, self.config.retries)
        last_err = ""
        for attempt in range(1, max_attempts + 1):
            if self._cancel_current.is_set() or self.handles.stop_event.is_set():
                return DownloadResult(ok=False, error="canceled")
            if not self.handles.network.online:
                self.store.set_status(item.id, M.WAITING_NET, "")
                self.handles.network.wait_online(timeout=60)
                self.store.set_status(item.id, M.DOWNLOADING, "")

            result = runner.download(item.url, item_id=item.id, overrides=overrides)
            if result.ok:
                return result
            last_err = result.error
            if self._is_terminal(last_err):
                break
            self.store.increment_retry(item.id)
            backoff = min(60.0, 1.5 ** attempt)
            retry_log.info(
                "[item %s] attempt %s/%s failed (%s) - backing off %.1fs",
                item.id, attempt, max_attempts, last_err, backoff,
            )
            # Pausable backoff so cancel/pause is responsive.
            end = time.monotonic() + backoff
            while time.monotonic() < end:
                if self._cancel_current.is_set() or self.handles.stop_event.is_set():
                    return DownloadResult(ok=False, error="canceled")
                time.sleep(0.2)
        return DownloadResult(ok=False, error=last_err or "exhausted retries")

    def _on_progress(self, item_id: int, evt: ProgressEvent) -> None:
        if evt.status == "downloading":
            self.store.update_progress(
                item_id,
                progress=round(evt.percent, 2),
                speed=evt.speed,
                eta=evt.eta,
                downloaded=evt.downloaded,
                total=evt.total,
            )
        if self.handles.progress_cb:
            try:
                self.handles.progress_cb(item_id, evt)
            except Exception:  # pragma: no cover
                log.exception("progress callback failed")

    def _update_status(self, item_id: int, status: str, error: str) -> None:
        self.store.set_status(item_id, status, error)
        if self.handles.status_cb:
            self.handles.status_cb(item_id, status, error)

    @staticmethod
    def _is_terminal(err: str) -> bool:
        msg = (err or "").lower()
        return any(
            tok in msg
            for tok in (
                "private video", "video unavailable", "removed by the user",
                "not available in your country", "account terminated",
                "post not found", "this video is no longer available",
            )
        )

    @staticmethod
    def _is_skippable_error(err: str) -> bool:
        msg = (err or "").lower()
        return any(
            tok in msg
            for tok in (
                "private video", "video unavailable", "removed by the user",
                "not available", "post not found", "this content isn",
                "no longer available",
            )
        )
