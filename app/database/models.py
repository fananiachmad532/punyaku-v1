"""Plain dataclasses mirroring rows in the SQLite queue store."""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional


# Status values
PENDING = "pending"
QUEUED = "queued"
DOWNLOADING = "downloading"
PAUSED = "paused"
COMPLETED = "completed"
FAILED = "failed"
SKIPPED = "skipped"
CANCELED = "canceled"
WAITING_NET = "waiting_network"

ACTIVE_STATES = {QUEUED, DOWNLOADING, PAUSED, WAITING_NET, PENDING}
TERMINAL_STATES = {COMPLETED, FAILED, SKIPPED, CANCELED}


@dataclass
class QueueItem:
    id: Optional[int] = None
    url: str = ""
    platform: str = "unknown"
    title: str = ""
    uploader: str = ""
    duration: int = 0
    upload_date: str = ""
    status: str = PENDING
    progress: float = 0.0
    speed: str = ""
    eta: str = ""
    bytes_downloaded: int = 0
    bytes_total: int = 0
    retry_count: int = 0
    priority: int = 100  # lower runs first
    position: int = 0
    temp_path: str = ""
    final_path: str = ""
    error: str = ""
    options_json: str = ""  # serialized per-item ydl_opts overrides
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    finished_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
