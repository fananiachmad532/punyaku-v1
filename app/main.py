"""Application entrypoint for Batch Downloader Pro."""
from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
from pathlib import Path
from typing import List, Optional

from .database.store import QueueStore
from .ffmpeg.installer import ensure as ensure_ffmpeg
from .queue.manager import QueueManager
from .settings.config import ConfigStore, get_store
from .updater.ytdlp_updater import maybe_auto_update, update as ytdlp_update
from .utils.logging_setup import configure as configure_logging
from .utils.logging_setup import get_logger, install_crash_handler


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Batch Downloader Pro")
    p.add_argument("--safe-mode", action="store_true", help="Skip background updates and ffmpeg auto-install at startup.")
    p.add_argument("--debug", action="store_true", help="Enable verbose logging.")
    p.add_argument("--headless", action="store_true", help="Run without launching the GUI (for smoke tests).")
    p.add_argument("--add", nargs="*", default=[], help="URLs to enqueue and exit (headless).")
    return p.parse_args(argv)


def _maybe_background_setup(cfg_store: ConfigStore, safe_mode: bool) -> None:
    if safe_mode:
        return
    cfg = cfg_store.config
    log = get_logger("setup")

    def _worker() -> None:
        # FFmpeg (silent best-effort).
        try:
            loc = ensure_ffmpeg(cfg.ffmpeg_dir)
            log.info("FFmpeg ready at %s (%s)", loc.directory, loc.source)
        except Exception as exc:  # broad: network/IO errors during install
            log.warning("FFmpeg auto-install failed: %s", exc)

        # yt-dlp auto-update check.
        if cfg.auto_update_ytdlp:
            try:
                info = maybe_auto_update(cfg.log_dir, cfg.update_check_interval_hours)
                if info and info.needs_update:
                    log.info("Updating yt-dlp %s -> %s", info.current, info.latest)
                    ytdlp_update()
            except Exception as exc:  # broad: yt-dlp / pip errors
                log.warning("yt-dlp update check failed: %s", exc)

    threading.Thread(target=_worker, name="bg-setup", daemon=True).start()


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)

    cfg_store = get_store()
    cfg = cfg_store.config

    level = logging.DEBUG if args.debug else logging.INFO
    configure_logging(cfg.log_dir, level=level)
    install_crash_handler(cfg.log_dir)

    log = get_logger("app")
    log.info("Starting Batch Downloader Pro (debug=%s, safe=%s)", args.debug, args.safe_mode)

    store = QueueStore(cfg.db_path)
    manager = QueueManager(store, cfg)
    manager.start()

    _maybe_background_setup(cfg_store, args.safe_mode)

    # Headless mode: enqueue URLs and exit (useful for CI / smoke tests).
    if args.headless:
        if args.add:
            ids = manager.enqueue_urls(args.add)
            print(f"Enqueued {len(ids)} item(s).")
        print("Headless mode: manager running. Press Ctrl+C to exit.")
        try:
            import time

            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            manager.stop()
        return 0

    # GUI mode.
    try:
        from PySide6.QtWidgets import QApplication

        from .ui.main_window import MainWindow
    except ImportError as exc:  # pragma: no cover - install issue
        print(f"PySide6 is required for the GUI: {exc}", file=sys.stderr)
        print("Install with: pip install PySide6", file=sys.stderr)
        manager.stop()
        return 1

    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow(store=store, manager=manager, cfg_store=cfg_store)
    win.show()
    code = app.exec()
    manager.stop()
    return int(code)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
