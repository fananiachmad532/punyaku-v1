"""Queue manager: orchestrates worker pool + global queue state.

Public API used by the UI:

    qm = QueueManager(store, config)
    qm.start()
    qm.enqueue_urls([...])
    qm.pause_all() / qm.resume_all() / qm.cancel_item(id)
    qm.reorder([id1, id2, ...])
    qm.stop()

Progress and status events are delivered via ``set_callbacks``.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Iterable, List, Optional

from ..database import models as M
from ..database.store import QueueStore
from ..downloader.expander import expand
from ..downloader.ytdlp_runner import ProgressEvent
from ..settings.config import AppConfig
from ..utils.antibot import UserAgentPool
from ..utils.logging_setup import get_logger
from ..utils.network import NetworkMonitor
from ..utils.platform_detect import classify, is_valid_supported_url
from ..workers.download_worker import DownloadWorker, WorkerHandles

log = get_logger("download")

ProgressCallback = Callable[[int, ProgressEvent], None]
StatusCallback = Callable[[int, str, str], None]
QueueChangedCallback = Callable[[], None]


class QueueManager:
    def __init__(self, store: QueueStore, config: AppConfig) -> None:
        self.store = store
        self.config = config
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._network = NetworkMonitor(interval=5.0)
        self._workers: List[DownloadWorker] = []
        self._ua_pool = UserAgentPool(config.user_agents)
        self._progress_cb: Optional[ProgressCallback] = None
        self._status_cb: Optional[StatusCallback] = None
        self._queue_changed_cb: Optional[QueueChangedCallback] = None
        self._lock = threading.RLock()

    # ----- lifecycle -----
    def set_callbacks(
        self,
        on_progress: Optional[ProgressCallback] = None,
        on_status: Optional[StatusCallback] = None,
        on_queue_changed: Optional[QueueChangedCallback] = None,
    ) -> None:
        self._progress_cb = on_progress
        self._status_cb = on_status
        self._queue_changed_cb = on_queue_changed

    def start(self) -> None:
        with self._lock:
            if self._workers:
                return
            self._stop_event.clear()
            self._pause_event.clear()
            self._network.start()
            handles = WorkerHandles(
                stop_event=self._stop_event,
                pause_event=self._pause_event,
                network=self._network,
                progress_cb=self._wrap_progress,
                status_cb=self._wrap_status,
            )
            for i in range(max(1, self.config.max_concurrent_downloads)):
                w = DownloadWorker(
                    name=f"worker-{i+1}",
                    store=self.store,
                    config=self.config,
                    ua_pool=self._ua_pool,
                    handles=handles,
                )
                w.start()
                self._workers.append(w)
            log.info("QueueManager started with %s workers", len(self._workers))

    def stop(self, timeout: float = 5.0) -> None:
        with self._lock:
            self._stop_event.set()
            for w in self._workers:
                w.cancel_current()
            for w in self._workers:
                w.join(timeout=timeout)
            self._workers.clear()
            self._network.stop()
        log.info("QueueManager stopped")

    # ----- queue ops -----
    def enqueue_urls(self, urls: Iterable[str], priority: int = 100) -> List[int]:
        added: List[int] = []
        items: List[M.QueueItem] = []
        for raw in urls:
            url = (raw or "").strip()
            if not url:
                continue
            if not is_valid_supported_url(url):
                log.warning("Skipping unsupported URL: %s", url)
                continue
            try:
                expanded = expand(url, self.config)
            except Exception as exc:  # pragma: no cover - defensive
                log.warning("expand failed for %s: %s", url, exc)
                expanded = [url]
            for u in expanded:
                info = classify(u)
                items.append(
                    M.QueueItem(
                        url=u,
                        platform=info.platform,
                        status=M.PENDING,
                        priority=priority,
                    )
                )
        with self._lock:
            for it in items:
                new_id = self.store.add_item(it)
                added.append(new_id)
        if added:
            self._notify_queue_changed()
            log.info("Enqueued %s items", len(added))
        return added

    def remove_item(self, item_id: int) -> None:
        # If it's the current download, cancel it first.
        self._cancel_worker_for(item_id)
        self.store.remove(item_id)
        self._notify_queue_changed()

    def cancel_item(self, item_id: int) -> None:
        if not self._cancel_worker_for(item_id):
            self.store.set_status(item_id, M.CANCELED, "")
        self._notify_queue_changed()

    def retry_item(self, item_id: int) -> None:
        self.store.update(
            item_id,
            status=M.PENDING,
            error="",
            progress=0.0,
            speed="",
            eta="",
            finished_at=0.0,
        )
        self._notify_queue_changed()

    def pause_all(self) -> None:
        self._pause_event.set()
        self.store.pause_all_active()
        for w in list(self._workers):
            w.cancel_current()
        self._notify_queue_changed()
        log.info("Paused all downloads")

    def resume_all(self) -> None:
        self.store.resume_all_paused()
        self._pause_event.clear()
        self._notify_queue_changed()
        log.info("Resumed all downloads")

    def reorder(self, ordered_ids: List[int]) -> None:
        self.store.reorder(ordered_ids)
        self._notify_queue_changed()

    def clear_finished(self) -> int:
        n = self.store.clear_terminal()
        if n:
            self._notify_queue_changed()
        return n

    def list_items(self, statuses: Optional[List[str]] = None) -> List[M.QueueItem]:
        return self.store.all_items(statuses)

    def history(self, limit: int = 500) -> List[M.QueueItem]:
        return self.store.history(limit)

    def stats(self) -> dict:
        return self.store.stats()

    # ----- helpers -----
    def _cancel_worker_for(self, item_id: int) -> bool:
        for w in self._workers:
            if w.current_item_id == item_id:
                w.cancel_current()
                # Wait briefly for the worker to surrender the item.
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline and w.current_item_id == item_id:
                    time.sleep(0.05)
                return True
        return False

    def _wrap_progress(self, item_id: int, evt: ProgressEvent) -> None:
        if self._progress_cb:
            self._progress_cb(item_id, evt)

    def _wrap_status(self, item_id: int, status: str, error: str) -> None:
        if self._status_cb:
            self._status_cb(item_id, status, error)
        # Status transitions count as queue changes for the UI.
        self._notify_queue_changed()

    def _notify_queue_changed(self) -> None:
        if self._queue_changed_cb:
            try:
                self._queue_changed_cb()
            except Exception:  # pragma: no cover
                log.exception("queue changed callback failed")
