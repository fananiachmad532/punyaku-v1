"""Expand playlist / channel URLs into a flat list of video URLs.

We use yt-dlp's ``extract_flat`` mode so this is cheap.
"""
from __future__ import annotations

from typing import List, Optional

from ..settings.config import AppConfig
from ..utils.logging_setup import get_logger
from ..utils.platform_detect import classify
from .ytdlp_runner import YtdlpRunner

log = get_logger("ytdlp")


def expand(url: str, config: AppConfig, runner: Optional[YtdlpRunner] = None) -> List[str]:
    """Return a list of concrete video URLs for *url*.

    For single-video URLs the input is returned unchanged. For playlist /
    channel URLs we expand using yt-dlp ``extract_flat``.
    """
    info = classify(url)
    if not (info.is_playlist or info.is_channel):
        return [url]
    runner = runner or YtdlpRunner(config)
    data = runner.extract_info(url)
    if not data:
        log.warning("expand: extract_info empty for %s", url)
        return [url]
    entries = data.get("entries") or []
    out: List[str] = []
    seen: set[str] = set()
    for entry in entries:
        if not entry:
            continue
        u = entry.get("url") or entry.get("webpage_url") or ""
        if u and not u.startswith("http"):
            # extract_flat sometimes returns video ids only; rebuild URL.
            vid = entry.get("id")
            if vid:
                u = f"https://www.youtube.com/watch?v={vid}"
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    if not out:
        return [url]
    return out
