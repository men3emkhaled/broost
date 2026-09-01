@echo off
chcp 65001 >nul
title Broost POS - Create Desktop Shortcut

set "TARGET_PATH=%~dp0dist\BroostPOS\Launch_BroostPOS.bat"
set "ICO_PATH=%~dp0dist\BroostPOS\logo.ico"
set "WORK_DIR=%~dp0dist\BroostPOS"

echo Creating Desktop shortcut for Broost POS...

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $d = [Environment]::GetFolderPath('Desktop'); $s = $ws.CreateShortcut([System.IO.Path]::Combine($d, 'Broost POS.lnk')); $s.TargetPath = '%TARGET_PATH%'; $s.WorkingDirectory = '%WORK_DIR%'; if (Test-Path '%ICO_PATH%') { $s.IconLocation = '%ICO_PATH%' }; $s.Description = 'Broost POS'; $s.Save();"

if %errorlevel% neq 0 (
    echo [ERROR] Failed to create shortcut.
) else (
    echo [OK] Desktop shortcut created successfully on Desktop!
)
pause
