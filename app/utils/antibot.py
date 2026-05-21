"""Anti-bot helpers: user-agent rotation + randomized request delay.

Kept tiny on purpose - yt-dlp does the heavy lifting; we just feed it
sane headers and a small jitter between worker dispatches.
"""
from __future__ import annotations

import random
import time
from typing import Dict, Iterable, List


class UserAgentPool:
    """Round-robin / random user-agent picker."""

    def __init__(self, agents: Iterable[str]) -> None:
        self._agents: List[str] = [a for a in agents if a]
        self._i = 0

    def next(self) -> str:
        if not self._agents:
            return ""
        ua = self._agents[self._i % len(self._agents)]
        self._i += 1
        return ua

    def random(self) -> str:
        return random.choice(self._agents) if self._agents else ""


def build_headers(user_agent: str, referer: str = "") -> Dict[str, str]:
    """Build a realistic set of HTTP headers for yt-dlp ``http_headers``."""
    headers: Dict[str, str] = {
        "User-Agent": user_agent,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "*/*",
        "Sec-Fetch-Mode": "navigate",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def jitter_sleep(min_ms: int, max_ms: int) -> None:
    """Sleep for a uniformly random duration between min/max milliseconds."""
    lo = max(0, int(min_ms))
    hi = max(lo, int(max_ms))
    if hi == 0:
        return
    time.sleep(random.uniform(lo / 1000.0, hi / 1000.0))


def platform_referer(platform: str) -> str:
    return {
        "youtube": "https://www.youtube.com/",
        "tiktok": "https://www.tiktok.com/",
        "instagram": "https://www.instagram.com/",
    }.get(platform, "")
