"""yt-dlp update orchestration.

We use yt-dlp as a Python library, so "updating" means running ``pip install
--upgrade yt-dlp`` inside the current interpreter. We expose a function that
checks the installed version against PyPI and another that performs the update.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

from ..utils.logging_setup import get_logger

log = get_logger("ytdlp")

_PYPI_URL = "https://pypi.org/pypi/yt-dlp/json"


@dataclass(frozen=True)
class VersionInfo:
    current: str
    latest: str

    @property
    def needs_update(self) -> bool:
        return bool(self.latest) and self.current != self.latest


def current_version() -> str:
    try:
        import yt_dlp  # type: ignore

        return getattr(yt_dlp.version, "__version__", "0")  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - yt-dlp not installed yet
        return "0"


def latest_version(timeout: float = 8.0) -> str:
    try:
        r = requests.get(_PYPI_URL, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return str(data.get("info", {}).get("version", ""))
    except (requests.RequestException, json.JSONDecodeError):
        return ""


def check() -> VersionInfo:
    return VersionInfo(current_version(), latest_version())


def update() -> bool:
    """Run ``pip install --upgrade yt-dlp`` in this interpreter.

    Returns True on success.
    """
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"]
    log.info("Updating yt-dlp: %s", " ".join(cmd))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if proc.returncode == 0:
            log.info("yt-dlp updated")
            return True
        log.error("yt-dlp update failed: %s", proc.stderr.strip())
        return False
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        log.error("yt-dlp update exception: %s", exc)
        return False


_STAMP_NAME = ".ytdlp_update_check"


def maybe_auto_update(state_dir: str | Path, interval_hours: int) -> Optional[VersionInfo]:
    """Run an update check at most once every ``interval_hours``.

    Returns the version info when a check ran, otherwise None. Caller is
    responsible for invoking :func:`update` if ``needs_update``.
    """
    if interval_hours <= 0:
        return None
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    stamp = state_dir / _STAMP_NAME
    now = time.time()
    if stamp.exists() and (now - stamp.stat().st_mtime) < interval_hours * 3600:
        return None
    info = check()
    try:
        stamp.write_text(str(now))
    except OSError:
        pass
    log.info("yt-dlp version check: current=%s latest=%s", info.current, info.latest)
    return info
