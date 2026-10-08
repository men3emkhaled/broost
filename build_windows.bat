@echo off
setlocal
cd /d "%~dp0"
if not "%BROOST_CLEAN_HOST_CONFIRMED%"=="1" (
    echo Build this release on a scanned, clean Windows machine.
    echo Set BROOST_CLEAN_HOST_CONFIRMED=1 there before running this script.
    exit /b 2
)
python -m PyInstaller --noconfirm --clean BroostPOS.spec || exit /b 1
python -m PyInstaller --noconfirm --clean BroostGuard.spec || exit /b 1
copy /Y "dist\CashierSystemGuard.exe" "dist\BroostPOS\CashierSystemGuard.exe" >nul || exit /b 1
set "ISCC_EXE="
for %%P in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe") do if exist "%%~P" set "ISCC_EXE=%%~P"
if not defined ISCC_EXE for /f "delims=" %%P in ('where iscc 2^>nul') do if not defined ISCC_EXE set "ISCC_EXE=%%P"
if not defined ISCC_EXE (
    echo Inno Setup 6 ISCC.exe is required to create the installer.
    exit /b 3
)
if not exist "release_offline" mkdir "release_offline" || exit /b 1
"%ISCC_EXE%" setup.iss || exit /b 1
if not exist "release_offline\Broost_Offline_Setup_2.2.exe" exit /b 1
echo Offline installer ready in release_offline\Broost_Offline_Setup_2.2.exe
