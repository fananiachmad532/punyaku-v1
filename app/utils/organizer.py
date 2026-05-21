"""Decide the destination folder for a download based on user prefs."""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Optional

from ..settings.config import AppConfig
from .filename import sanitize


def target_directory(
    config: AppConfig,
    platform: str,
    uploader: Optional[str] = None,
    upload_date: Optional[str] = None,
) -> Path:
    """Return the directory where the download should land.

    ``upload_date`` is the yt-dlp ``upload_date`` field (YYYYMMDD).
    """
    base = Path(config.download_dir)
    parts: list[str] = []
    if config.organize_by_platform and platform:
        parts.append({"youtube": "YouTube", "tiktok": "TikTok", "instagram": "Instagram"}.get(platform, platform.title()))
    if config.organize_by_uploader and uploader:
        parts.append(sanitize(uploader))
    if config.organize_by_date:
        parts.append(_format_date(upload_date))
    out = base.joinpath(*parts) if parts else base
    out.mkdir(parents=True, exist_ok=True)
    return out


def _format_date(upload_date: Optional[str]) -> str:
    if upload_date and len(upload_date) == 8 and upload_date.isdigit():
        try:
            d = _dt.date(int(upload_date[:4]), int(upload_date[4:6]), int(upload_date[6:8]))
            return d.strftime("%Y-%m")
        except ValueError:
            pass
    return _dt.date.today().strftime("%Y-%m")
