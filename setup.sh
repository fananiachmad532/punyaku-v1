#!/usr/bin/env bash
# POSIX equivalent of setup.bat
set -euo pipefail

cd "$(dirname "$0")"

echo "[1/5] Checking Python..."
if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3.12+ is required. Install it from https://www.python.org/downloads/"
    exit 1
fi
python3 --version

echo "[2/5] Creating virtual environment..."
if [ ! -d venv ]; then
    python3 -m venv venv
fi

# shellcheck disable=SC1091
source venv/bin/activate

echo "[3/5] Upgrading pip..."
pip install --upgrade pip wheel setuptools

echo "[4/5] Installing requirements..."
pip install -r requirements.txt

echo "[5/5] Checking FFmpeg..."
if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "FFmpeg is not on PATH. The app will auto-download a static build on first launch."
else
    ffmpeg -version | head -n1
fi

echo "Setup complete. Run ./run.sh to launch the application."
