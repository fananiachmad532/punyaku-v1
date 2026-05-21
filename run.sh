#!/usr/bin/env bash
# POSIX launcher equivalent to run.bat
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d venv ]; then
    echo "[setup] creating virtual environment..."
    python3 -m venv venv
fi

# shellcheck disable=SC1091
source venv/bin/activate

if ! python -c "import yt_dlp, PySide6, requests" >/dev/null 2>&1; then
    echo "[setup] installing dependencies..."
    pip install --upgrade pip
    pip install -r requirements.txt
fi

exec python -m app.main "$@"
