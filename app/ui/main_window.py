"""Main PySide6 window for the batch downloader.

Layout (top-down):
  - Header with app title + global actions
  - Stat cards (total / active / completed / failed)
  - Splitter:
      * Left: URL input (multi-line) + Add / Import / Paste buttons
      * Right: Queue table with progress bars + per-row actions
  - Footer: status bar + speed/eta summary
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..database import models as M
from ..database.store import QueueStore
from ..ffmpeg.installer import ensure as ensure_ffmpeg
from ..queue.manager import QueueManager
from ..settings.config import AppConfig, ConfigStore, get_store
from ..updater.ytdlp_updater import maybe_auto_update, update as run_ytdlp_update
from ..utils.io_helpers import (
    export_history_csv,
    export_session_json,
    load_session_json,
    load_urls_from_file,
    load_urls_from_text,
)
from ..utils.logging_setup import get_logger
from ..utils.platform_detect import pretty_platform
from .signals import make_bus
from .style import dark_stylesheet

log = get_logger("ui")


COLUMNS = [
    "#",
    "Platform",
    "Title / URL",
    "Status",
    "Progress",
    "Speed",
    "ETA",
    "Retries",
]


class MainWindow(QMainWindow):
    def __init__(self, store: QueueStore, manager: QueueManager, cfg_store: ConfigStore) -> None:
        super().__init__()
        self.store = store
        self.manager = manager
        self.cfg_store = cfg_store
        self.config = cfg_store.config

        self.setWindowTitle("Batch Downloader Pro")
        self.resize(1180, 720)
        self.setStyleSheet(dark_stylesheet(self.config.accent_color))

        self.bus = make_bus()
        self.manager.set_callbacks(
            on_progress=lambda iid, evt: self.bus.progress.emit(iid, _evt_to_dict(evt)),
            on_status=lambda iid, st, err: self.bus.status_changed.emit(iid, st, err),
            on_queue_changed=lambda: self.bus.queue_changed.emit(),
        )
        self.bus.queue_changed.connect(self._refresh_queue)
        self.bus.progress.connect(self._on_progress)
        self.bus.status_changed.connect(lambda *_: self._refresh_queue())

        self._row_by_id: Dict[int, int] = {}

        self._build_ui()
        self._build_toolbar()
        self._refresh_queue()
        self._refresh_stats()

        # Periodic stats refresh (cheap; just counts).
        self._stats_timer = QTimer(self)
        self._stats_timer.setInterval(1500)
        self._stats_timer.timeout.connect(self._refresh_stats)
        self._stats_timer.start()

    # ---- UI building ----
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        root.addWidget(self._build_stats_row())

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self._build_input_panel())
        splitter.addWidget(self._build_queue_panel())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        root.addWidget(splitter, 1)

        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("Ready")

    def _build_stats_row(self) -> QWidget:
        wrap = QWidget()
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.stat_widgets: Dict[str, QLabel] = {}
        for key, title in (
            ("total", "Total"),
            ("active", "Active"),
            ("completed", "Completed"),
            ("failed", "Failed"),
            ("speed", "Total Speed"),
        ):
            card = QFrame()
            card.setObjectName("card")
            v = QVBoxLayout(card)
            v.setContentsMargins(16, 12, 16, 12)
            t = QLabel(title)
            t.setObjectName("statTitle")
            val = QLabel("0")
            val.setObjectName("statValue")
            v.addWidget(t)
            v.addWidget(val)
            self.stat_widgets[key] = val
            layout.addWidget(card, 1)
        return wrap

    def _build_input_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        layout.addWidget(QLabel("<b>Paste URLs</b> (one per line, or paste raw text)"))
        self.url_input = QPlainTextEdit()
        self.url_input.setPlaceholderText(
            "https://youtube.com/...\nhttps://www.tiktok.com/@user/video/...\nhttps://www.instagram.com/reel/...\n"
        )
        self.url_input.setMinimumHeight(160)
        self.url_input.setAcceptDrops(True)
        layout.addWidget(self.url_input, 1)

        # Options.
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["best", "1080", "720", "480", "360", "audio"])
        idx = max(0, self.quality_combo.findText(self.config.preferred_quality))
        self.quality_combo.setCurrentIndex(idx)

        self.container_combo = QComboBox()
        self.container_combo.addItems(["mp4", "mkv", "webm"])
        self.container_combo.setCurrentText(self.config.container)

        self.audio_only = QCheckBox("Audio only")
        self.audio_only.setChecked(self.config.audio_only)

        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setRange(1, 10)
        self.concurrent_spin.setValue(self.config.max_concurrent_downloads)

        self.cookie_combo = QComboBox()
        self.cookie_combo.addItems(["none", "chrome", "edge", "firefox", "brave"])
        cur = self.config.cookie_browser or "none"
        self.cookie_combo.setCurrentText(cur)

        form.addRow("Quality", self.quality_combo)
        form.addRow("Container", self.container_combo)
        form.addRow("", self.audio_only)
        form.addRow("Concurrent", self.concurrent_spin)
        form.addRow("Cookies from", self.cookie_combo)
        layout.addLayout(form)

        # Action buttons.
        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("Add to queue")
        self.btn_add.setObjectName("primary")
        self.btn_add.clicked.connect(self._on_add_clicked)
        self.btn_paste = QPushButton("Paste")
        self.btn_paste.clicked.connect(self._on_paste_clicked)
        self.btn_import = QPushButton("Import TXT/CSV")
        self.btn_import.clicked.connect(self._on_import_clicked)
        btn_row.addWidget(self.btn_add, 1)
        btn_row.addWidget(self.btn_paste)
        btn_row.addWidget(self.btn_import)
        layout.addLayout(btn_row)

        return panel

    def _build_queue_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header row.
        header = QHBoxLayout()
        title = QLabel("<b>Download queue</b>")
        header.addWidget(title)
        header.addStretch(1)
        self.btn_pause = QPushButton("Pause all")
        self.btn_pause.clicked.connect(self.manager.pause_all)
        self.btn_resume = QPushButton("Resume all")
        self.btn_resume.clicked.connect(self.manager.resume_all)
        self.btn_clear = QPushButton("Clear finished")
        self.btn_clear.clicked.connect(self._on_clear_finished)
        header.addWidget(self.btn_pause)
        header.addWidget(self.btn_resume)
        header.addWidget(self.btn_clear)
        layout.addLayout(header)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(False)
        self.table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.table.setDragEnabled(True)
        self.table.setAcceptDrops(True)
        self.table.setDropIndicatorShown(True)
        self.table.setShowGrid(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for i in [0, 1, 3, 5, 6, 7]:
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(4, 220)

        self.table.cellDoubleClicked.connect(self._on_row_double_click)
        layout.addWidget(self.table, 1)

        # Row action bar.
        actions = QHBoxLayout()
        self.btn_retry = QPushButton("Retry selected")
        self.btn_retry.clicked.connect(self._on_retry_selected)
        self.btn_cancel = QPushButton("Cancel selected")
        self.btn_cancel.clicked.connect(self._on_cancel_selected)
        self.btn_remove = QPushButton("Remove selected")
        self.btn_remove.setObjectName("danger")
        self.btn_remove.clicked.connect(self._on_remove_selected)
        self.btn_open = QPushButton("Open folder")
        self.btn_open.clicked.connect(self._on_open_folder)
        actions.addWidget(self.btn_retry)
        actions.addWidget(self.btn_cancel)
        actions.addStretch(1)
        actions.addWidget(self.btn_open)
        actions.addWidget(self.btn_remove)
        layout.addLayout(actions)

        return panel

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main", self)
        tb.setMovable(False)
        self.addToolBar(tb)

        save_session = QAction("Save session", self)
        save_session.setShortcut(QKeySequence("Ctrl+S"))
        save_session.triggered.connect(self._on_save_session)
        tb.addAction(save_session)

        load_session = QAction("Load session", self)
        load_session.setShortcut(QKeySequence("Ctrl+O"))
        load_session.triggered.connect(self._on_load_session)
        tb.addAction(load_session)

        tb.addSeparator()

        export_hist = QAction("Export history CSV", self)
        export_hist.triggered.connect(self._on_export_history)
        tb.addAction(export_hist)

        tb.addSeparator()

        update_ytdlp = QAction("Update yt-dlp", self)
        update_ytdlp.triggered.connect(self._on_update_ytdlp)
        tb.addAction(update_ytdlp)

        open_dl = QAction("Open downloads", self)
        open_dl.triggered.connect(lambda: _open_path(self.config.download_dir))
        tb.addAction(open_dl)

        open_logs = QAction("Open logs", self)
        open_logs.triggered.connect(lambda: _open_path(self.config.log_dir))
        tb.addAction(open_logs)

    # ---- handlers ----
    def _collect_options_from_ui(self) -> None:
        """Persist the quick-options in the side panel back to config."""
        self.cfg_store.update(
            preferred_quality=self.quality_combo.currentText(),
            container=self.container_combo.currentText(),
            audio_only=self.audio_only.isChecked(),
            max_concurrent_downloads=int(self.concurrent_spin.value()),
            cookie_browser="" if self.cookie_combo.currentText() == "none" else self.cookie_combo.currentText(),
        )
        # NB: worker count change applies on next start; we warn the user.

    def _on_add_clicked(self) -> None:
        self._collect_options_from_ui()
        urls = load_urls_from_text(self.url_input.toPlainText())
        if not urls:
            self.statusBar().showMessage("No URLs detected in the input.", 4000)
            return
        added = self.manager.enqueue_urls(urls)
        self.url_input.clear()
        self.statusBar().showMessage(f"Added {len(added)} item(s) to the queue.", 4000)

    def _on_paste_clicked(self) -> None:
        cb = QApplication.clipboard()
        text = cb.text() if cb else ""
        if text:
            self.url_input.setPlainText((self.url_input.toPlainText() + "\n" + text).strip())

    def _on_import_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import URLs",
            os.path.expanduser("~"),
            "URL lists (*.txt *.csv);;All files (*)",
        )
        if not path:
            return
        urls = load_urls_from_file(path)
        if not urls:
            QMessageBox.information(self, "Import", "No URLs found in the selected file.")
            return
        added = self.manager.enqueue_urls(urls)
        self.statusBar().showMessage(f"Imported {len(added)} URL(s).", 4000)

    def _on_clear_finished(self) -> None:
        n = self.manager.clear_finished()
        self.statusBar().showMessage(f"Cleared {n} finished item(s).", 3000)

    def _selected_ids(self) -> List[int]:
        ids: List[int] = []
        for row in {idx.row() for idx in self.table.selectedIndexes()}:
            item = self.table.item(row, 0)
            if item is None:
                continue
            iid = item.data(Qt.ItemDataRole.UserRole)
            if iid is not None:
                ids.append(int(iid))
        return ids

    def _on_retry_selected(self) -> None:
        for iid in self._selected_ids():
            self.manager.retry_item(iid)

    def _on_cancel_selected(self) -> None:
        for iid in self._selected_ids():
            self.manager.cancel_item(iid)

    def _on_remove_selected(self) -> None:
        for iid in self._selected_ids():
            self.manager.remove_item(iid)

    def _on_open_folder(self) -> None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            _open_path(self.config.download_dir)
            return
        iid = self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        item = self.store.get(int(iid)) if iid is not None else None
        target = item.final_path if item and item.final_path else self.config.download_dir
        target_dir = str(Path(target).parent) if Path(target).is_file() else str(target)
        _open_path(target_dir)

    def _on_row_double_click(self, row: int, _col: int) -> None:
        iid = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if iid is None:
            return
        it = self.store.get(int(iid))
        if not it:
            return
        msg = (
            f"URL: {it.url}\n"
            f"Platform: {pretty_platform(it.platform)}\n"
            f"Status: {it.status}\n"
            f"Final path: {it.final_path or '-'}\n"
            f"Error: {it.error or '-'}"
        )
        QMessageBox.information(self, "Queue item details", msg)

    def _on_save_session(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save session", "session.json", "JSON (*.json)"
        )
        if not path:
            return
        items = [
            {"url": it.url, "platform": it.platform, "priority": it.priority}
            for it in self.manager.list_items()
        ]
        export_session_json(items, path)
        self.statusBar().showMessage(f"Session saved to {path}", 4000)

    def _on_load_session(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load session", "", "JSON (*.json)"
        )
        if not path:
            return
        rows = load_session_json(path)
        urls = [r.get("url", "") for r in rows if r.get("url")]
        added = self.manager.enqueue_urls(urls)
        self.statusBar().showMessage(f"Loaded {len(added)} URL(s) from {path}", 4000)

    def _on_export_history(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export history", "history.csv", "CSV (*.csv)"
        )
        if not path:
            return
        rows = [it.to_dict() for it in self.manager.history(limit=5000)]
        export_history_csv(rows, path)
        self.statusBar().showMessage(f"History exported to {path}", 4000)

    def _on_update_ytdlp(self) -> None:
        ok = run_ytdlp_update()
        QMessageBox.information(
            self,
            "yt-dlp update",
            "yt-dlp updated successfully." if ok else "yt-dlp update failed. See logs.",
        )

    # ---- refresh ----
    def _refresh_queue(self) -> None:
        items = self.manager.list_items()
        self.table.setRowCount(len(items))
        self._row_by_id.clear()
        for row, it in enumerate(items):
            if it.id is None:
                continue
            self._row_by_id[it.id] = row
            num = QTableWidgetItem(str(row + 1))
            num.setData(Qt.ItemDataRole.UserRole, it.id)
            num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, num)

            self.table.setItem(row, 1, QTableWidgetItem(pretty_platform(it.platform)))
            title_or_url = it.title or it.url
            self.table.setItem(row, 2, QTableWidgetItem(title_or_url))

            status = QTableWidgetItem(_pretty_status(it.status))
            status.setForeground(_status_brush(it.status))
            self.table.setItem(row, 3, status)

            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(int(it.progress or 0))
            bar.setFormat(f"{it.progress:.1f}%")
            self.table.setCellWidget(row, 4, bar)

            self.table.setItem(row, 5, QTableWidgetItem(it.speed or ""))
            self.table.setItem(row, 6, QTableWidgetItem(it.eta or ""))
            self.table.setItem(row, 7, QTableWidgetItem(str(it.retry_count)))

    def _on_progress(self, item_id: int, evt_dict: dict) -> None:
        row = self._row_by_id.get(item_id)
        if row is None:
            return
        bar = self.table.cellWidget(row, 4)
        if isinstance(bar, QProgressBar):
            pct = float(evt_dict.get("percent") or 0.0)
            bar.setValue(int(pct))
            bar.setFormat(f"{pct:.1f}%")
        if (it := self.table.item(row, 5)):
            it.setText(str(evt_dict.get("speed") or ""))
        if (it := self.table.item(row, 6)):
            it.setText(str(evt_dict.get("eta") or ""))

    def _refresh_stats(self) -> None:
        s = self.manager.stats()
        self.stat_widgets["total"].setText(str(s.get("total", 0)))
        self.stat_widgets["active"].setText(str(s.get("active", 0)))
        self.stat_widgets["completed"].setText(str(s.get("completed", 0)))
        self.stat_widgets["failed"].setText(str(s.get("failed", 0)))
        # Total speed = sum of active item speeds (rough).
        total = 0.0
        for it in self.manager.list_items([M.DOWNLOADING]):
            total += _parse_speed(it.speed)
        self.stat_widgets["speed"].setText(_format_bytes_per_sec(total))

    # ---- close ----
    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            self.manager.stop(timeout=3.0)
        except Exception:  # pragma: no cover
            log.exception("error while stopping queue manager")
        super().closeEvent(event)


def _evt_to_dict(evt) -> dict:  # type: ignore[no-untyped-def]
    return {
        "status": evt.status,
        "percent": evt.percent,
        "speed": evt.speed,
        "eta": evt.eta,
        "downloaded": evt.downloaded,
        "total": evt.total,
        "filename": evt.filename,
        "fragment_index": evt.fragment_index,
        "fragment_count": evt.fragment_count,
    }


def _pretty_status(s: str) -> str:
    return {
        M.PENDING: "Pending",
        M.QUEUED: "Queued",
        M.DOWNLOADING: "Downloading",
        M.PAUSED: "Paused",
        M.COMPLETED: "Completed",
        M.FAILED: "Failed",
        M.SKIPPED: "Skipped",
        M.CANCELED: "Canceled",
        M.WAITING_NET: "Waiting net",
    }.get(s, s.title())


def _status_brush(s: str):  # type: ignore[no-untyped-def]
    from PySide6.QtGui import QBrush, QColor

    color = {
        M.COMPLETED: "#4cd964",
        M.FAILED: "#ff5b6b",
        M.SKIPPED: "#ffa940",
        M.CANCELED: "#8b95a5",
        M.DOWNLOADING: "#3da9fc",
        M.WAITING_NET: "#ffa940",
        M.PAUSED: "#ffa940",
    }.get(s, "#e6e8eb")
    return QBrush(QColor(color))


def _parse_speed(s: str) -> float:
    if not s:
        return 0.0
    try:
        num, unit = s.split(" ", 1)
        v = float(num)
    except ValueError:
        return 0.0
    mult = {"B/s": 1, "KB/s": 1024, "MB/s": 1024 ** 2, "GB/s": 1024 ** 3}
    return v * mult.get(unit, 1)


def _format_bytes_per_sec(bps: float) -> str:
    if bps <= 0:
        return "0 B/s"
    units = ["B/s", "KB/s", "MB/s", "GB/s"]
    v = bps
    i = 0
    while v >= 1024 and i < len(units) - 1:
        v /= 1024
        i += 1
    return f"{v:.1f} {units[i]}"


def _open_path(path: str) -> None:
    """Open a folder in the system file manager (best effort)."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    try:
        if os.name == "nt":
            os.startfile(str(p))  # type: ignore[attr-defined]
        elif os.sys.platform == "darwin":  # type: ignore[attr-defined]
            import subprocess

            subprocess.Popen(["open", str(p)])  # noqa: S603,S607
        else:
            import subprocess

            subprocess.Popen(["xdg-open", str(p)])  # noqa: S603,S607
    except OSError:
        logging.getLogger("ui").warning("Could not open path %s", p)
