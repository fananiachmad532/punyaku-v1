# Batch Downloader Pro

Professional batch downloader desktop application for **YouTube**, **YouTube Shorts**, **TikTok**, **Instagram**, and **Instagram Reels**. Built with Python 3.12+, `yt-dlp`, `FFmpeg`, and `PySide6`.

The app is designed for **massive batch downloads** - hundreds or thousands of URLs at a time - without freezing, crashing, or losing progress. It uses a persistent SQLite queue, a thread-based worker pool, automatic retry with exponential backoff, automatic resume after crashes, and a network monitor that pauses workers when the connection drops.

## Features

- **Multi URL input** - paste many URLs, drag in a `.txt` / `.csv`, or use the `Import` button.
- **Smart download queue** - priority ordering, pause/resume globally or per-item, retry, cancel, drag-and-drop reorder, persistent across crashes/restarts.
- **Parallel download engine** - 1-10 concurrent workers (default 3) with adaptive bandwidth limit.
- **Advanced retry** - automatic retry of HTTP errors, fragment failures, network drops, DNS errors, with exponential backoff.
- **Resume system** - resumes interrupted downloads, including after a crash, internet drop, or restart.
- **SQLite queue database** - every item's URL, platform, status, progress, retries, temp path, final path, and error log persists to disk.
- **Massive batch mode** - workers + DB are tuned for thousands of URLs; queue is chunked, memory is constant.
- **Auto skip broken URLs** - private / deleted / blocked URLs are skipped instead of stalling the queue.
- **Smart format fallback** - if your preferred quality (e.g. 1080p MP4) fails, the app drops to 720p, then MP4 universal, then plain `best`.
- **FFmpeg auto installer** - detects FFmpeg on PATH, otherwise downloads a static build into the app data dir.
- **yt-dlp auto updater** - daily version check + `pip install --upgrade yt-dlp` button.
- **Cookie support** - `chrome`, `edge`, `firefox`, `brave`, or a Netscape-format cookies file.
- **Anti-bot helpers** - user-agent rotation, realistic headers, randomized request delays.
- **Safe filename system** - unicode-safe sanitizer, Windows reserved-name guard, length cap, anti-duplicate suffixing.
- **Dedicated worker threads** - downloads never run on the UI thread, so the app stays responsive.
- **Network monitor** - polls connectivity; workers wait offline instead of burning retries.
- **Professional logging** - rotating files for app/error/retry/ffmpeg/ytdlp/download/network/crash.
- **Playlist & channel expander** - YouTube playlists and channel feeds are expanded into individual items.
- **File organizer** - downloads grouped by platform, uploader, and/or upload month.
- **Import/export** - import URLs from TXT/CSV; export download history to CSV; save/load queue sessions to JSON.
- **Modern dark UI** - PySide6 with a custom dark stylesheet, stat cards, animated progress bars, and drag-and-drop queue reorder.

## Supported platforms

- YouTube (videos, Shorts, playlists, channels, music)
- TikTok (videos, user profiles)
- Instagram (posts, Reels)

Any other URL is automatically skipped during enqueue.

## Requirements

- **Python** 3.12 or newer (3.11 works too)
- **FFmpeg** (auto-installed if missing)
- Windows 10/11, macOS 12+, or Linux

## Quick start (Windows)

```bat
git clone https://github.com/fananiachmad532/punyaku-v1
cd punyaku-v1
setup.bat
run.bat
```

`setup.bat` creates a virtual environment, installs all dependencies, and prepares the runtime folders.
`run.bat` activates the venv and launches the GUI.

Optional flags for `run.bat`:
- `run.bat --safe-mode` skips background auto-update and FFmpeg install (useful for diagnostics).
- `run.bat --debug` enables verbose logging.

## Quick start (macOS / Linux)

```bash
git clone https://github.com/fananiachmad532/punyaku-v1
cd punyaku-v1
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python -m app.main
```

If you want a launcher script:

```bash
./run.sh        # equivalent of run.bat on POSIX systems
```

## Build a standalone Windows EXE

```bat
setup.bat
build.bat
```

The build output lands in `dist\BatchDownloaderPro\`.

## Project structure

```
punyaku-v1/
├── app/
│   ├── main.py                # entrypoint (argparse + Qt bootstrap)
│   ├── settings/config.py     # AppConfig dataclass + JSON store
│   ├── database/              # SQLite queue + history models
│   ├── downloader/            # yt-dlp wrapper, format selector, playlist expander
│   ├── workers/               # download worker threads
│   ├── queue/                 # queue manager (worker pool coordinator)
│   ├── ffmpeg/                # FFmpeg detect + auto installer
│   ├── updater/               # yt-dlp auto-updater
│   ├── ui/                    # PySide6 main window + dark stylesheet
│   └── utils/                 # logging, filename, platform detect, network, antibot, io
├── logs/                      # runtime logs (rotating)
├── assets/                    # icons / static assets
├── requirements.txt
├── config.json                # default config (regenerated at first launch)
├── .env.example
├── main.spec                  # PyInstaller spec
├── setup.bat / run.bat / build.bat
└── README.md
```

## Configuration

All settings live in `config.json` next to the app. They are loaded into [`AppConfig`](app/settings/config.py) and you can change them either by editing the file or via the side panel in the UI (the GUI persists changes on each enqueue). Key fields:

| Field                       | Default                  | Description |
| --------------------------- | ------------------------ | ----------- |
| `download_dir`              | `~/Downloads/BatchDownloaderPro` | Where finished files land. |
| `temp_dir`                  | `<user data>/temp`       | Partial downloads + merge dir. |
| `db_path`                   | `<user data>/queue.sqlite3` | Persistent queue. |
| `max_concurrent_downloads`  | `3`                      | Parallel workers (1-10 recommended). |
| `concurrent_fragments`      | `5`                      | yt-dlp `concurrent_fragment_downloads`. |
| `retries` / `fragment_retries` | `10`                  | Per-item retry budget. |
| `socket_timeout`            | `30`                     | Seconds before a stalled socket is killed. |
| `rate_limit_bps`            | `0`                      | Total bandwidth cap in bytes/sec (0 = unlimited). |
| `preferred_quality`         | `"1080"`                 | One of `best`, `1080`, `720`, `480`, `360`, `audio`. |
| `audio_only`                | `false`                  | Audio-only mode (MP3 by default). |
| `container`                 | `"mp4"`                  | Preferred output container. |
| `cookie_browser`            | `""`                     | `chrome`, `edge`, `firefox`, `brave`, or empty. |
| `cookie_file`               | `""`                     | Path to a Netscape cookies.txt (takes precedence). |
| `organize_by_platform`      | `true`                   | Sort downloads into `YouTube/`, `TikTok/`, `Instagram/` subfolders. |
| `auto_update_ytdlp`         | `true`                   | Check PyPI for a newer yt-dlp at startup. |
| `theme` / `accent_color`    | `dark` / `#3da9fc`       | UI theme color. |

## Logging

The app keeps separate rotating logs (2 MB x 5 each) per concern:

```
<user data>/logs/
  app.log
  error.log
  retry.log
  ffmpeg.log
  ytdlp.log
  download.log
  network.log
  crash.log
```

Open the folder anytime with **Toolbar → Open logs**.

## How resume + recovery works

1. Every queue item is written to SQLite as soon as you enqueue it.
2. The worker calls yt-dlp with `--continue` (`continuedl=True`), so partial files in the temp dir resume on the next attempt.
3. If the app is killed mid-download, the next startup detects items stuck in `downloading` / `waiting_network` and resets them to `pending`. The worker pool picks them up again automatically.
4. If a single URL fails terminally (private / deleted / blocked), the worker marks it `skipped` and moves on - it never blocks the queue.

## Anti-bot tips

- For YouTube age-restricted or private videos, set `cookie_browser` to whichever browser you are logged into.
- For Instagram, login cookies are mandatory. Either log in via Chrome/Edge/Firefox and set `cookie_browser`, or supply a Netscape-format `cookie_file`.
- Workers stagger their start with a randomized delay (`request_delay_min_ms` / `request_delay_max_ms`) to avoid burst patterns.
- The user-agent pool rotates through Windows Chrome, macOS Safari, Linux Chrome, and iOS Safari strings.

## Troubleshooting

| Symptom | Fix |
| ------- | --- |
| `ffmpeg not found` errors at startup | Open the toolbar -> **Open logs** -> check `ffmpeg.log`. If the auto-install failed (no network), install FFmpeg manually and add it to PATH. |
| Many `403 Forbidden` errors | Set `cookie_browser` to a browser you're logged into, and reduce `max_concurrent_downloads`. |
| App seems stuck on "Waiting net" | The network monitor detected an outage. It auto-resumes when connectivity comes back. |
| Want to wipe the queue | Delete the `*.sqlite3*` files in the user data dir (path is in `config.json` -> `db_path`). |

## License

Personal use. See repository for additional terms.
