@echo off
chcp 65001 >nul
title Broost POS - Create Desktop Shortcut

:: ── حدد المسار الكامل للـ exe ──────────────────────────
set "EXE_PATH=%~dp0BroostPOS.exe"
set "ICO_PATH=%~dp0logo.ico"
set "WORK_DIR=%~dp0"

:: تأكد إن الملف موجود
if not exist "%EXE_PATH%" (
    echo [ERROR] BroostPOS.exe not found next to this script.
    echo         Please run this script from inside the BroostPOS folder.
    pause
    exit /b 1
)

echo Creating Desktop shortcut for Broost POS...

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$WshShell = New-Object -ComObject WScript.Shell;" ^
  "$Desktop = [Environment]::GetFolderPath('Desktop');" ^
  "$Shortcut = $WshShell.CreateShortcut($Desktop + '\Broost POS.lnk');" ^
  "$Shortcut.TargetPath   = '%EXE_PATH%';" ^
  "$Shortcut.WorkingDirectory = '%WORK_DIR%';" ^
  "$Shortcut.IconLocation = '%ICO_PATH%';" ^
  "$Shortcut.Description  = 'Broost POS - نظام نقاط البيع';" ^
  "$Shortcut.Save();"

if %errorlevel% neq 0 (
    echo [ERROR] Failed to create shortcut.
) else (
    echo [OK] Desktop shortcut "Broost POS" created successfully!
)
pause
