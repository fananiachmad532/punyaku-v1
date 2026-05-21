@echo off
REM ============================================================
REM   Batch Downloader Pro - Setup
REM   - Creates a virtual environment
REM   - Installs Python dependencies
REM   - Validates Python + FFmpeg + yt-dlp
REM ============================================================
setlocal ENABLEEXTENSIONS

cd /d "%~dp0"
set "LOG=%~dp0logs\setup.log"
if not exist "%~dp0logs" mkdir "%~dp0logs"

echo.>>"%LOG%"
echo === Setup run at %date% %time% ===>>"%LOG%"

echo.
echo [1/7] Checking Python...
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not on PATH.
    echo         Install Python 3.12+ from https://www.python.org/downloads/
    echo [ERROR] Python missing>>"%LOG%"
    pause
    exit /b 1
)
python --version
python --version >>"%LOG%" 2>&1

echo.
echo [2/7] Creating virtual environment...
if not exist venv (
    python -m venv venv >>"%LOG%" 2>&1
    if errorlevel 1 (
        echo [ERROR] Failed to create venv. See logs\setup.log
        pause
        exit /b 1
    )
)

echo.
echo [3/7] Activating virtual environment...
call "%~dp0venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] Could not activate venv.
    pause
    exit /b 1
)

echo.
echo [4/7] Upgrading pip...
python -m pip install --upgrade pip wheel setuptools >>"%LOG%" 2>&1

echo.
echo [5/7] Installing dependencies from requirements.txt...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install failed. See output above and logs\setup.log
    pause
    exit /b 1
)

echo.
echo [6/7] Updating yt-dlp...
python -m pip install --upgrade yt-dlp >>"%LOG%" 2>&1

echo.
echo [7/7] Checking FFmpeg...
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo FFmpeg not found on PATH. The application will auto-download a static
    echo build into the user data directory on first launch.
) else (
    ffmpeg -version | findstr /C:"ffmpeg version"
)

REM Create folder structure used at runtime.
if not exist downloads mkdir downloads
if not exist temp mkdir temp

echo.
echo Setup complete. Run run.bat to launch the application.
echo.
pause
endlocal
