"""Import / export helpers for batch URL lists and history dumps."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable, List, Sequence

from .platform_detect import extract_urls


def load_urls_from_text(text: str) -> List[str]:
    """Parse URLs from a free-form text blob (one per line OR mixed)."""
    urls: List[str] = []
    seen = set()
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Allow lines with extra text around the URL, e.g. "1. https://..."
        for u in extract_urls(line) or [line]:
            if u not in seen and u.lower().startswith(("http://", "https://")):
                seen.add(u)
                urls.append(u)
    return urls


def load_urls_from_file(path: str | Path) -> List[str]:
    """Read a .txt or .csv file and return de-duplicated URLs.

    For CSV: looks for a column called ``url`` (case-insensitive), otherwise
    treats the first column as the URL.
    """
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".csv":
        return _load_csv(p)
    return load_urls_from_text(p.read_text(encoding="utf-8", errors="replace"))


def _load_csv(p: Path) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    with p.open(newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.reader(fh)
        rows = list(reader)
        if not rows:
            return out
        header = [c.strip().lower() for c in rows[0]]
        url_col = header.index("url") if "url" in header else 0
        start = 1 if "url" in header else 0
        for row in rows[start:]:
            if not row or url_col >= len(row):
                continue
            url = row[url_col].strip()
            if url and url.lower().startswith(("http://", "https://")) and url not in seen:
                seen.add(url)
                out.append(url)
    return out


def export_history_csv(rows: Sequence[dict], path: str | Path) -> None:
    """Dump a list of dict rows to CSV (history export)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        p.write_text("", encoding="utf-8")
        return
    fieldnames: List[str] = list(rows[0].keys())
    with p.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def export_session_json(rows: Iterable[dict], path: str | Path) -> None:
    """Save queue items as JSON for restore."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(list(rows), indent=2, ensure_ascii=False), encoding="utf-8")


def load_session_json(path: str | Path) -> List[dict]:
    p = Path(path)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return list(data) if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []
