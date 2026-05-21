"""URL platform detection for supported targets.

Returns one of:
- "youtube"          (incl. shorts, music, m.youtube)
- "youtube_playlist"
- "tiktok"
- "instagram"
- "unknown"

Also exposes ``is_playlist_url`` and ``is_channel_url`` heuristics.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, parse_qs

_YT_HOSTS = ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be")
_TIKTOK_HOSTS = ("tiktok.com", "www.tiktok.com", "vm.tiktok.com", "vt.tiktok.com", "m.tiktok.com")
_IG_HOSTS = ("instagram.com", "www.instagram.com")

_URL_RE = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)


@dataclass(frozen=True)
class UrlInfo:
    url: str
    platform: str
    is_playlist: bool
    is_channel: bool
    is_shorts: bool


def _normalize_host(host: str) -> str:
    return host.lower().lstrip(".")


def detect_platform(url: str) -> str:
    try:
        host = _normalize_host(urlparse(url).netloc)
    except ValueError:
        return "unknown"
    if not host:
        return "unknown"
    if host in _YT_HOSTS or host.endswith(".youtube.com"):
        return "youtube"
    if host in _TIKTOK_HOSTS or host.endswith(".tiktok.com"):
        return "tiktok"
    if host in _IG_HOSTS or host.endswith(".instagram.com"):
        return "instagram"
    return "unknown"


def classify(url: str) -> UrlInfo:
    parsed = urlparse(url)
    host = _normalize_host(parsed.netloc)
    path = parsed.path or ""
    qs = parse_qs(parsed.query or "")
    platform = detect_platform(url)

    is_playlist = False
    is_channel = False
    is_shorts = False

    if platform == "youtube":
        is_playlist = bool(qs.get("list")) or path.startswith("/playlist")
        is_shorts = "/shorts/" in path
        is_channel = (
            path.startswith("/@")
            or path.startswith("/channel/")
            or path.startswith("/c/")
            or path.startswith("/user/")
        )
    elif platform == "tiktok":
        is_channel = path.startswith("/@") and "/video/" not in path
        # TikTok doesn't really have playlists; treat collections as playlist.
        is_playlist = "/collection/" in path or "/playlist/" in path
    elif platform == "instagram":
        is_channel = bool(re.fullmatch(r"/[^/]+/?", path))
        is_playlist = path.startswith("/stories/") or path.startswith("/reels/")
    return UrlInfo(
        url=url,
        platform=platform,
        is_playlist=is_playlist,
        is_channel=is_channel,
        is_shorts=is_shorts,
    )


def extract_urls(text: str) -> list[str]:
    """Extract all URLs from a blob of text (paste-friendly)."""
    return [m.group(0) for m in _URL_RE.finditer(text or "")]


def is_valid_supported_url(url: str) -> bool:
    return detect_platform(url) != "unknown"


def pretty_platform(platform: str) -> str:
    return {
        "youtube": "YouTube",
        "tiktok": "TikTok",
        "instagram": "Instagram",
    }.get(platform, "Unknown")
