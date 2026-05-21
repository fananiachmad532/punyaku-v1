"""yt-dlp invocation wrapper.

This module builds an options dict, runs the download with progress callbacks,
applies fallback strategies, and reports a normalized result.

It is fully synchronous - workers call it from a thread / process and surface
progress via the supplied callback.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..settings.config import AppConfig
from ..utils.antibot import UserAgentPool, build_headers, platform_referer
from ..utils.filename import unique_path
from ..utils.logging_setup import get_logger
from ..utils.organizer import target_directory
from ..utils.platform_detect import detect_platform, classify
from .format_selector import build_format, fallback_chain

log = get_logger("ytdlp")
download_log = get_logger("download")


@dataclass
class ProgressEvent:
    status: str  # downloading | finished | error
    percent: float = 0.0
    speed: str = ""
    eta: str = ""
    downloaded: int = 0
    total: int = 0
    filename: str = ""
    fragment_index: int = 0
    fragment_count: int = 0


@dataclass
class DownloadResult:
    ok: bool
    final_path: str = ""
    title: str = ""
    uploader: str = ""
    duration: int = 0
    upload_date: str = ""
    platform: str = ""
    error: str = ""
    info: Dict[str, Any] = field(default_factory=dict)


# Marker exception used internally to short-circuit yt-dlp on cancel.
class _Canceled(Exception):
    pass


class YtdlpLogger:
    """Adapt yt-dlp's logger interface to our channel logger."""

    def __init__(self, item_id: Optional[int]) -> None:
        self.item_id = item_id
        self._logger = get_logger("ytdlp")

    def debug(self, msg: str) -> None:
        if msg.startswith("[debug] "):
            return
        self._logger.debug("[%s] %s", self.item_id, msg)

    def info(self, msg: str) -> None:
        self._logger.info("[%s] %s", self.item_id, msg)

    def warning(self, msg: str) -> None:
        self._logger.warning("[%s] %s", self.item_id, msg)

    def error(self, msg: str) -> None:
        self._logger.error("[%s] %s", self.item_id, msg)


class YtdlpRunner:
    """High-level wrapper around :class:`yt_dlp.YoutubeDL`."""

    def __init__(
        self,
        config: AppConfig,
        on_progress: Optional[Callable[[ProgressEvent], None]] = None,
        ua_pool: Optional[UserAgentPool] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        pause_check: Optional[Callable[[], bool]] = None,
    ) -> None:
        self.config = config
        self.on_progress = on_progress
        self.ua_pool = ua_pool or UserAgentPool(config.user_agents)
        self.cancel_check = cancel_check or (lambda: False)
        self.pause_check = pause_check or (lambda: False)
        self._last_event: float = 0.0

    # ----- public API -----
    def extract_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Best-effort metadata-only extraction (no download).

        Returns None on failure rather than raising so the queue can keep going.
        """
        try:
            import yt_dlp  # type: ignore
        except ImportError as exc:  # pragma: no cover
            log.error("yt-dlp not installed: %s", exc)
            return None
        opts = self._base_opts(item_id=None)
        opts["quiet"] = True
        opts["skip_download"] = True
        opts["extract_flat"] = "in_playlist"
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception as exc:  # broad: yt-dlp surfaces many error types
            log.warning("extract_info failed for %s: %s", url, exc)
            return None

    def download(
        self,
        url: str,
        item_id: Optional[int],
        overrides: Optional[Dict[str, Any]] = None,
    ) -> DownloadResult:
        try:
            import yt_dlp  # type: ignore
        except ImportError as exc:  # pragma: no cover
            return DownloadResult(ok=False, error=f"yt-dlp not installed: {exc}")

        info = classify(url)
        platform = info.platform if info.platform != "unknown" else detect_platform(url)
        formats = fallback_chain(self.config.preferred_quality, self.config.container)
        if self.config.audio_only:
            formats = ["bestaudio/best"]

        last_error: str = ""
        last_info: Dict[str, Any] = {}
        for attempt, fmt in enumerate(formats, start=1):
            if self.cancel_check():
                return DownloadResult(ok=False, error="canceled")

            opts = self._base_opts(item_id=item_id, platform=platform)
            opts["format"] = fmt
            if overrides:
                opts.update(overrides)
            self._apply_output_template(opts, platform)
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    extracted = ydl.extract_info(url, download=True)
                    last_info = extracted or {}
                    final_path = self._pick_final_path(ydl, extracted)
                return DownloadResult(
                    ok=True,
                    final_path=str(final_path or ""),
                    title=str(last_info.get("title", "")),
                    uploader=str(last_info.get("uploader", "")),
                    duration=int(last_info.get("duration") or 0),
                    upload_date=str(last_info.get("upload_date", "") or ""),
                    platform=platform,
                    info=last_info,
                )
            except _Canceled:
                return DownloadResult(ok=False, error="canceled")
            except Exception as exc:  # noqa: BLE001 - yt-dlp surfaces many types
                last_error = str(exc)
                log.warning(
                    "Attempt %s failed for %s (format=%s): %s",
                    attempt, url, fmt, last_error,
                )
                if self._is_terminal_error(last_error):
                    break
        return DownloadResult(ok=False, error=last_error or "unknown error", info=last_info)

    # ----- internals -----
    def _base_opts(self, item_id: Optional[int], platform: str = "") -> Dict[str, Any]:
        cfg = self.config
        ua = self.ua_pool.next() if self.ua_pool else ""
        opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,  # we deliver progress via hooks
            "continuedl": True,
            "retries": cfg.retries,
            "fragment_retries": cfg.fragment_retries,
            "extractor_retries": cfg.retries,
            "file_access_retries": 5,
            "concurrent_fragment_downloads": cfg.concurrent_fragments,
            "socket_timeout": cfg.socket_timeout,
            "nocheckcertificate": True,
            "ignoreerrors": False,
            "noplaylist": True,  # queue manager handles playlists explicitly
            "logger": YtdlpLogger(item_id),
            "progress_hooks": [self._progress_hook],
            "postprocessor_hooks": [self._postprocessor_hook],
            "http_headers": build_headers(ua, platform_referer(platform)),
            "paths": {
                "home": str(target_directory(cfg, platform)),
                "temp": str(Path(cfg.temp_dir)),
            },
            "windowsfilenames": True,
            "restrictfilenames": False,
            "trim_file_name": 200,
            "merge_output_format": cfg.container if not cfg.audio_only else None,
        }
        # Rate limiting (yt-dlp expects bytes/sec, 0 = unlimited).
        if cfg.rate_limit_bps and cfg.rate_limit_bps > 0:
            opts["ratelimit"] = cfg.rate_limit_bps
        # Audio post-processing.
        if cfg.audio_only:
            opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": cfg.audio_format,
                    "preferredquality": "192",
                }
            ]
        # Cookies.
        if cfg.cookie_file:
            opts["cookiefile"] = cfg.cookie_file
        elif cfg.cookie_browser:
            opts["cookiesfrombrowser"] = (cfg.cookie_browser,)
        return opts

    def _apply_output_template(self, opts: Dict[str, Any], platform: str) -> None:
        outtmpl = self.config.filename_template
        opts["outtmpl"] = outtmpl

    def _pick_final_path(self, ydl: Any, info: Optional[Dict[str, Any]]) -> Optional[Path]:
        if not info:
            return None
        # Prefer requested_downloads, then filepath, then prepare_filename.
        downloads = info.get("requested_downloads") or []
        for d in downloads:
            p = d.get("filepath") or d.get("_filename")
            if p:
                return Path(p)
        try:
            return Path(ydl.prepare_filename(info))
        except Exception:  # pragma: no cover
            return None

    def _progress_hook(self, d: Dict[str, Any]) -> None:
        if self.cancel_check():
            raise _Canceled()
        # Coarse throttle: at most ~10 events/sec per download.
        now = time.monotonic()
        if d.get("status") == "downloading" and (now - self._last_event) < 0.1:
            return
        self._last_event = now

        status = d.get("status", "")
        downloaded = int(d.get("downloaded_bytes") or 0)
        total = int(d.get("total_bytes") or d.get("total_bytes_estimate") or 0)
        pct = (downloaded / total * 100.0) if total else 0.0
        speed_b = d.get("speed") or 0
        speed = _fmt_speed(speed_b)
        eta = _fmt_eta(d.get("eta"))
        filename = str(d.get("filename") or "")
        evt = ProgressEvent(
            status=status,
            percent=pct,
            speed=speed,
            eta=eta,
            downloaded=downloaded,
            total=total,
            filename=filename,
            fragment_index=int(d.get("fragment_index") or 0),
            fragment_count=int(d.get("fragment_count") or 0),
        )
        if self.on_progress:
            try:
                self.on_progress(evt)
            except Exception:  # pragma: no cover - callback safety
                logging.getLogger("download").exception("progress callback failed")

    def _postprocessor_hook(self, d: Dict[str, Any]) -> None:
        if self.cancel_check():
            raise _Canceled()
        if d.get("status") == "started" and self.on_progress:
            try:
                self.on_progress(ProgressEvent(status="postprocess", filename=str(d.get("postprocessor") or "")))
            except Exception:  # pragma: no cover
                pass

    @staticmethod
    def _is_terminal_error(msg: str) -> bool:
        msg_l = msg.lower()
        for needle in (
            "video unavailable",
            "private video",
            "this video is private",
            "removed by the user",
            "not available in your country",
            "account terminated",
            "violating youtube's policy",
            "post not found",
            "blocked it on copyright",
            "this content isn",
        ):
            if needle in msg_l:
                return True
        return False


def _fmt_speed(speed_b: Any) -> str:
    try:
        v = float(speed_b or 0)
    except (TypeError, ValueError):
        return ""
    if v <= 0:
        return ""
    units = ["B/s", "KB/s", "MB/s", "GB/s"]
    i = 0
    while v >= 1024 and i < len(units) - 1:
        v /= 1024
        i += 1
    return f"{v:.1f} {units[i]}"


def _fmt_eta(eta: Any) -> str:
    try:
        v = int(eta or 0)
    except (TypeError, ValueError):
        return ""
    if v <= 0:
        return ""
    if v < 60:
        return f"{v}s"
    if v < 3600:
        m, s = divmod(v, 60)
        return f"{m}m{s:02d}s"
    h, rem = divmod(v, 3600)
    m, _ = divmod(rem, 60)
    return f"{h}h{m:02d}m"
