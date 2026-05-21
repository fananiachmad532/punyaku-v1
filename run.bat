@echo off
REM ============================================================
REM   Batch Downloader Pro - Run
REM ============================================================
setlocal ENABLEEXTENSIONS

cd /d "%~dp0"

if not exist venv (
    echo [ERROR] Virtual environment not found. Please run setup.bat first.
    pause
    exit /b 1
)

call "%~dp0venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] Could not activate venv. Please run setup.bat again.
    pause
    exit /b 1
)

REM Light dependency sanity check.
python -c "import yt_dlp, PySide6, requests" 2>nul
if errorlevel 1 (
    echo [WARN] Dependencies appear incomplete. Re-running setup...
    call "%~dp0setup.bat"
)

set ARGS=
if "%~1"=="--safe-mode" set ARGS=--safe-mode
if "%~1"=="--debug" set ARGS=--debug

python -m app.main %ARGS%
set RC=%ERRORLEVEL%

if not %RC%==0 (
    echo.
    echo Application exited with code %RC%. Logs are in logs\.
    pause
)
endlocal
