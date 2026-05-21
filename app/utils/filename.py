"""Safe filename sanitizer.

Rules:
- Strip / collapse illegal characters across Windows + POSIX
- Preserve unicode
- Trim filename to a safe length (255 bytes UTF-8)
- Avoid Windows reserved names (CON, PRN, AUX, NUL, COM1.., LPT1..)
- Produce unique filename in a target dir to avoid overwriting downloads
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Iterable

# Characters illegal on Windows + most filesystems.
_ILLEGAL = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_WHITESPACE = re.compile(r"[\s]+")
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_MAX_BYTES = 240  # leave headroom for path + extension


def _truncate_utf8(name: str, max_bytes: int = _MAX_BYTES) -> str:
    encoded = name.encode("utf-8")
    if len(encoded) <= max_bytes:
        return name
    # Cut at byte boundary and then decode safely.
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def sanitize(name: str, replacement: str = "_") -> str:
    """Return a filename-safe version of *name*.

    Empty / all-illegal input maps to "untitled".
    """
    if not name:
        return "untitled"
    # NFC keeps composed unicode (good for filename display on all OSes).
    name = unicodedata.normalize("NFC", name)
    name = _ILLEGAL.sub(replacement, name)
    name = _WHITESPACE.sub(" ", name).strip(" .")
    if not name:
        return "untitled"
    base = Path(name).stem
    if base.upper() in _RESERVED:
        name = f"_{name}"
    return _truncate_utf8(name)


def unique_path(directory: Path | str, filename: str) -> Path:
    """Return a unique Path inside *directory* by suffixing (1), (2), ..."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / filename
    if not p.exists():
        return p
    stem, suffix = p.stem, p.suffix
    i = 1
    while True:
        candidate = directory / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def join_components(parts: Iterable[str]) -> str:
    """Join sanitized path components with the OS separator."""
    cleaned = [sanitize(p) for p in parts if p]
    return str(Path(*cleaned)) if cleaned else ""
