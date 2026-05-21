"""Centralized rotating-file logging.

Multiple log streams are kept separate so that high-volume download chatter
doesn't drown out the much rarer error / crash messages.
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Dict


_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured: Dict[str, bool] = {}


def _stream_handler() -> logging.Handler:
    h = logging.StreamHandler(stream=sys.stdout)
    h.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    return h


def _file_handler(path: Path, level: int) -> logging.Handler:
    path.parent.mkdir(parents=True, exist_ok=True)
    h = logging.handlers.RotatingFileHandler(
        path, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    h.setLevel(level)
    h.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    return h


def configure(log_dir: str | Path, level: int = logging.INFO) -> None:
    """Configure root + per-channel loggers. Idempotent."""
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    if not _configured.get("root"):
        root.setLevel(level)
        root.addHandler(_stream_handler())
        root.addHandler(_file_handler(log_dir / "app.log", level))
        _configured["root"] = True

    # Dedicated channels (still propagate to root so console works).
    channels = {
        "download": "download.log",
        "error": "error.log",
        "retry": "retry.log",
        "ffmpeg": "ffmpeg.log",
        "ytdlp": "ytdlp.log",
        "network": "network.log",
    }
    for name, fname in channels.items():
        key = f"channel:{name}"
        if _configured.get(key):
            continue
        lg = logging.getLogger(name)
        lg.addHandler(_file_handler(log_dir / fname, level))
        lg.setLevel(level)
        _configured[key] = True

    # Errors go to error.log via root error handler too.
    err_key = "channel:_root_error"
    if not _configured.get(err_key):
        root.addHandler(_file_handler(log_dir / "error.log", logging.ERROR))
        _configured[err_key] = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def install_crash_handler(log_dir: str | Path) -> None:
    """Capture unhandled exceptions to ``crash.log``."""
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    crash_log = log_dir / "crash.log"

    def _hook(exc_type, exc, tb):  # type: ignore[no-untyped-def]
        logging.getLogger("crash").critical(
            "Unhandled exception", exc_info=(exc_type, exc, tb)
        )
        # Also drop a dedicated dump so users can grab it easily.
        import traceback

        with crash_log.open("a", encoding="utf-8") as fh:
            fh.write("=" * 60 + "\n")
            traceback.print_exception(exc_type, exc, tb, file=fh)
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _hook
