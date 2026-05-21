@echo off
REM ============================================================
REM   Batch Downloader Pro - Build standalone EXE with PyInstaller
REM ============================================================
setlocal ENABLEEXTENSIONS

cd /d "%~dp0"

if not exist venv (
    echo [ERROR] Virtual environment not found. Run setup.bat first.
    pause
    exit /b 1
)

call "%~dp0venv\Scripts\activate.bat"

echo Cleaning previous build artifacts...
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

echo Building EXE with PyInstaller...
pyinstaller main.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    pause
    exit /b 1
)

echo.
echo Build complete. See dist\BatchDownloaderPro\
echo.
pause
endlocal
