@echo off
setlocal
cd /d "%~dp0"
if not "%BROOST_CLEAN_HOST_CONFIRMED%"=="1" (
    echo Build this release on a scanned, clean Windows machine.
    echo Set BROOST_CLEAN_HOST_CONFIRMED=1 there before running this script.
    exit /b 2
)
python -m PyInstaller --noconfirm BroostPOS.spec || exit /b 1
python -m PyInstaller --noconfirm BroostGuard.spec || exit /b 1
copy /Y "dist\CashierSystemGuard.exe" "dist\BroostPOS\CashierSystemGuard.exe" >nul || exit /b 1
echo Offline application ready in dist\BroostPOS
where iscc >nul 2>nul
if errorlevel 1 exit /b 0
iscc /DReleaseSourceDir="dist\BroostPOS" setup.iss
