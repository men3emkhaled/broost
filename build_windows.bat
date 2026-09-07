@echo off
setlocal
cd /d "%~dp0"
python scripts\build_windows_release.py %*
if errorlevel 1 (
    echo [ERROR] Build failed. Existing cashier installations were not changed.
    pause
    exit /b 1
)
pause
