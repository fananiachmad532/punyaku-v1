"""FFmpeg detection + auto installer.

Strategy:
1. Look for ``ffmpeg`` on PATH (works if the user installed it system-wide).
2. Look in our managed dir (``ffmpeg_dir`` from config).
3. If neither, download a static build from gyan.dev (Windows) or
   johnvansickle.com (Linux) and extract into ``ffmpeg_dir``.

We deliberately don't try to compile FFmpeg ourselves - we always grab a
prebuilt static binary.
"""
from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import requests

from ..utils.logging_setup import get_logger

log = get_logger("ffmpeg")

WINDOWS_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
LINUX_AMD64_URL = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
LINUX_ARM64_URL = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz"
MACOS_URL = "https://evermeet.cx/ffmpeg/getrelease/zip"  # universal binary zip


@dataclass(frozen=True)
class FFmpegLocation:
    ffmpeg: str
    ffprobe: str
    directory: str
    source: str  # "path", "managed", "installed"


class FFmpegError(RuntimeError):
    pass


def _which(name: str) -> Optional[str]:
    p = shutil.which(name)
    if p and Path(p).exists():
        return p
    return None


def _executable_name(base: str) -> str:
    return f"{base}.exe" if os.name == "nt" else base


def detect(managed_dir: str | Path) -> Optional[FFmpegLocation]:
    """Return location of an installed ffmpeg, if any."""
    # 1. PATH
    sys_ff = _which("ffmpeg")
    sys_fp = _which("ffprobe")
    if sys_ff and sys_fp and _validate(sys_ff):
        return FFmpegLocation(sys_ff, sys_fp, str(Path(sys_ff).parent), "path")

    # 2. Managed dir
    managed = Path(managed_dir)
    if managed.exists():
        ff = _find_in(managed, _executable_name("ffmpeg"))
        fp = _find_in(managed, _executable_name("ffprobe"))
        if ff and fp and _validate(ff):
            return FFmpegLocation(str(ff), str(fp), str(ff.parent), "managed")
    return None


def _find_in(root: Path, name: str) -> Optional[Path]:
    for p in root.rglob(name):
        if p.is_file():
            return p
    return None


def _validate(path: str) -> bool:
    try:
        out = subprocess.run(
            [path, "-version"], capture_output=True, text=True, timeout=10
        )
        return out.returncode == 0 and "ffmpeg" in (out.stdout + out.stderr).lower()
    except (OSError, subprocess.SubprocessError):
        return False


def install(
    managed_dir: str | Path,
    on_progress: Optional[Callable[[float, str], None]] = None,
) -> FFmpegLocation:
    """Download + extract a static FFmpeg into ``managed_dir``."""
    managed_dir = Path(managed_dir)
    managed_dir.mkdir(parents=True, exist_ok=True)

    url = _platform_url()
    log.info("Downloading FFmpeg from %s", url)
    if on_progress:
        on_progress(0.0, f"Downloading FFmpeg from {url}")

    tmp = Path(tempfile.mkdtemp(prefix="ffmpeg-dl-"))
    try:
        archive = tmp / Path(url).name
        _download_with_progress(url, archive, on_progress)

        if on_progress:
            on_progress(0.85, "Extracting archive...")
        _extract(archive, managed_dir)

        location = detect(managed_dir)
        if not location:
            raise FFmpegError("FFmpeg extracted but binaries not found")
        if on_progress:
            on_progress(1.0, f"FFmpeg installed to {location.directory}")
        log.info("FFmpeg installed to %s", location.directory)
        return location
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def ensure(
    managed_dir: str | Path,
    on_progress: Optional[Callable[[float, str], None]] = None,
) -> FFmpegLocation:
    """Return existing FFmpeg or install one. Adds it to PATH for child procs."""
    loc = detect(managed_dir)
    if not loc:
        loc = install(managed_dir, on_progress)
    # Make sure subprocesses (yt-dlp) can find it.
    _prepend_path(loc.directory)
    return loc


def _platform_url() -> str:
    sysname = platform.system().lower()
    machine = (platform.machine() or "").lower()
    if sysname == "windows":
        return WINDOWS_URL
    if sysname == "darwin":
        return MACOS_URL
    # Linux / others
    if "aarch64" in machine or "arm64" in machine:
        return LINUX_ARM64_URL
    return LINUX_AMD64_URL


def _download_with_progress(
    url: str,
    dest: Path,
    on_progress: Optional[Callable[[float, str], None]],
) -> None:
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with dest.open("wb") as fh:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue
                fh.write(chunk)
                done += len(chunk)
                if on_progress and total:
                    on_progress(0.8 * (done / total), f"Downloading FFmpeg... {done // 1024 // 1024} MB")


def _extract(archive: Path, target: Path) -> None:
    if archive.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(target)
    elif archive.name.endswith(".tar.xz") or archive.name.endswith(".tar.gz"):
        with tarfile.open(archive) as tf:
            tf.extractall(target)
    else:
        # Try zip first, then tar.
        try:
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(target)
        except zipfile.BadZipFile:
            with tarfile.open(archive) as tf:
                tf.extractall(target)

    if os.name != "nt":
        # Ensure +x on extracted binaries.
        for p in target.rglob("ffmpeg"):
            _chmod_exec(p)
        for p in target.rglob("ffprobe"):
            _chmod_exec(p)


def _chmod_exec(p: Path) -> None:
    try:
        st = p.stat()
        p.chmod(st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        pass


def _prepend_path(directory: str) -> None:
    sep = ";" if os.name == "nt" else ":"
    current = os.environ.get("PATH", "")
    if directory not in current.split(sep):
        os.environ["PATH"] = directory + sep + current
