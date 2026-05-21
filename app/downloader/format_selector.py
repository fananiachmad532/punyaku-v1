"""Build yt-dlp format selectors with sane platform-specific fallbacks."""
from __future__ import annotations


def build_format(quality: str, container: str = "mp4", audio_only: bool = False) -> str:
    """Return a yt-dlp ``format`` string.

    Falls back through several variants so a single failed combo doesn't kill
    the download:
      bestvideo+bestaudio[mp4] -> best[mp4] -> bestvideo+bestaudio -> best
    """
    if audio_only:
        return "bestaudio/best"

    q = (quality or "best").lower()
    cap = ""
    if q in {"1080", "720", "480", "360", "240"}:
        cap = f"[height<={q}]"
    elif q == "best":
        cap = ""
    elif q == "audio":
        return "bestaudio/best"

    cont = container.lower() if container else "mp4"
    return (
        f"bestvideo{cap}[ext={cont}]+bestaudio[ext=m4a]/"
        f"bestvideo{cap}+bestaudio/"
        f"best{cap}[ext={cont}]/"
        f"best{cap}/best"
    )


def fallback_chain(quality: str, container: str = "mp4") -> list[str]:
    """Return progressively-more-permissive format strings to try in order."""
    chain = [build_format(quality, container)]
    # Drop container preference.
    chain.append(build_format(quality, "mp4"))
    # Step down quality if a numeric quality was requested.
    if quality.isdigit():
        steps = ["1080", "720", "480", "360"]
        try:
            idx = steps.index(quality)
            for lower in steps[idx + 1 :]:
                chain.append(build_format(lower, container))
        except ValueError:
            pass
    # Final safety net.
    chain.append("best")
    # De-dupe while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for f in chain:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out
