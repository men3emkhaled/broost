@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Python environment missing. Run: py -3.12 -m venv .venv
    echo Then run: .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)
start "Broost POS Offline" ".venv\Scripts\pythonw.exe" "app.py"
