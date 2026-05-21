"""Application configuration loaded from JSON + env, with safe defaults.

The config is intentionally simple JSON so users can hand-edit it. Defaults
are written on first launch so the app is usable without any setup.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

APP_DIR_NAME = "BatchDownloaderPro"


def project_root() -> Path:
    """Return the directory containing the running ``app`` package.

    Falls back to the current working directory when frozen by PyInstaller.
    """
    here = Path(__file__).resolve()
    # app/settings/config.py -> repo root
    return here.parent.parent.parent


def user_data_dir() -> Path:
    """Per-user data dir for db/logs/temp/config."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming")))
    elif os.sys.platform == "darwin":  # type: ignore[attr-defined]
        base = Path.home() / "Library/Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    p = base / APP_DIR_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass
class AppConfig:
    """Top-level application configuration.

    Fields map 1:1 to keys in ``config.json``.
    """

    # Paths
    download_dir: str = str(Path.home() / "Downloads" / APP_DIR_NAME)
    temp_dir: str = str(user_data_dir() / "temp")
    db_path: str = str(user_data_dir() / "queue.sqlite3")
    log_dir: str = str(user_data_dir() / "logs")
    ffmpeg_dir: str = str(user_data_dir() / "ffmpeg")

    # Concurrency
    max_concurrent_downloads: int = 3
    concurrent_fragments: int = 5

    # Retry / network
    retries: int = 10
    fragment_retries: int = 10
    socket_timeout: int = 30
    request_delay_min_ms: int = 0
    request_delay_max_ms: int = 250

    # Bandwidth (bytes per second; 0 = unlimited)
    rate_limit_bps: int = 0

    # Format
    preferred_quality: str = "1080"  # "best", "1080", "720", "480", "audio"
    audio_only: bool = False
    audio_format: str = "mp3"
    container: str = "mp4"

    # Cookies
    cookie_browser: str = ""  # one of "", "chrome", "edge", "firefox", "brave"
    cookie_file: str = ""

    # Organizer
    organize_by_platform: bool = True
    organize_by_uploader: bool = False
    organize_by_date: bool = False
    filename_template: str = "%(title).150B [%(id)s].%(ext)s"

    # Updates
    auto_update_ytdlp: bool = True
    update_check_interval_hours: int = 24

    # UI
    theme: str = "dark"
    accent_color: str = "#3da9fc"

    # Misc
    user_agents: List[str] = field(
        default_factory=lambda: [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        ]
    )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        defaults = cls()
        merged: Dict[str, Any] = {**asdict(defaults), **(data or {})}
        # Drop keys that aren't fields anymore so we forward-compat cleanly.
        valid = {f for f in defaults.__dataclass_fields__}
        merged = {k: v for k, v in merged.items() if k in valid}
        return cls(**merged)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ConfigStore:
    """Loads and persists :class:`AppConfig` to ``config.json``."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else project_root() / "config.json"
        self.config = self._load()
        self._ensure_dirs()

    def _load(self) -> AppConfig:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                return AppConfig.from_dict(data)
            except (json.JSONDecodeError, OSError):
                # Fall through to defaults if the file is broken.
                pass
        cfg = AppConfig()
        self._write(cfg)
        return cfg

    def _write(self, cfg: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(cfg.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _ensure_dirs(self) -> None:
        for key in ("download_dir", "temp_dir", "log_dir", "ffmpeg_dir"):
            Path(getattr(self.config, key)).mkdir(parents=True, exist_ok=True)
        Path(self.config.db_path).parent.mkdir(parents=True, exist_ok=True)

    def save(self) -> None:
        self._write(self.config)

    def update(self, **kwargs: Any) -> AppConfig:
        for k, v in kwargs.items():
            if hasattr(self.config, k):
                setattr(self.config, k, v)
        self._ensure_dirs()
        self.save()
        return self.config


_store: Optional[ConfigStore] = None


def get_store() -> ConfigStore:
    """Singleton accessor for the global config store."""
    global _store
    if _store is None:
        _store = ConfigStore()
    return _store


def get_config() -> AppConfig:
    return get_store().config
