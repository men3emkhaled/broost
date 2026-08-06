@echo off
title Cashier System - Windows Build Tool
echo.
echo =====================================================
echo           Cashier System - Windows Build Tool
echo =====================================================
echo.

rem Step 0: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)

rem Step 1: Install / upgrade dependencies
echo [1/7] Installing dependencies...
python -m pip install PyQt6 pyinstaller -r requirements-web.txt --quiet
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo       Done.

rem Step 2: Clean previous build
echo [2/7] Cleaning previous build artifacts...
if exist "build" rmdir /s /q "build"
if exist "dist\BroostPOS" (
    rmdir /s /q "dist\BroostPOS" 2>nul
    del /f /q "dist\BroostPOS" 2>nul
)
if exist "dist\BroostPOS.exe" del /q "dist\BroostPOS.exe"
if exist "dist\BroostWebServer.exe" del /q "dist\BroostWebServer.exe"
if exist "BroostPOS.exe"      del /q "BroostPOS.exe"
if exist "CashierSystem_Setup.exe" del /q "CashierSystem_Setup.exe"
echo       Done.

rem Step 3: Build using spec file
echo [3/7] Compiling Cashier System...
python -m PyInstaller --noconfirm BroostPOS.spec
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Build failed.
    pause
    exit /b 1
)
echo       Done.

rem Step 4: Build the local website/admin server
echo [4/7] Compiling Broost Web Server...
python -m PyInstaller --noconfirm BroostWebServer.spec
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Web server build failed.
    pause
    exit /b 1
)
copy "dist\BroostWebServer.exe" "dist\BroostPOS\BroostWebServer.exe" >nul
echo       Done.

rem Step 5: Copy runtime data files
echo [5/7] Copying runtime data assets...

rem Database
if not exist "dist\BroostPOS\broost_pos.db" (
    if exist "broost_pos.db" (
        copy "broost_pos.db" "dist\BroostPOS\broost_pos.db" >nul
        echo       Copied broost_pos.db
    ) else (
        echo       [INFO] No database found.
    )
) else (
    echo       [SKIP] broost_pos.db already exists.
)

rem QR Code
if exist "facebook-qr.jpeg" (
    copy "facebook-qr.jpeg" "dist\BroostPOS\facebook-qr.jpeg" >nul
    echo       Copied facebook-qr.jpeg
)

rem Logo
if exist "logo.png" (
    copy "logo.png" "dist\BroostPOS\logo.png" >nul
    echo       Copied logo.png
)

rem Logo ICO
if exist "logo.ico" (
    copy "logo.ico" "dist\BroostPOS\logo.ico" >nul
    echo       Copied logo.ico
)

rem Backups folder
if not exist "dist\BroostPOS\backups" mkdir "dist\BroostPOS\backups"

echo       Done.

rem Step 6: Create launcher scripts inside dist
echo [6/7] Creating launcher scripts...
(
    echo @echo off
    echo cd /d "%%~dp0"
    echo start "" "BroostPOS.exe"
) > "dist\BroostPOS\Launch_BroostPOS.bat"
(
    echo @echo off
    echo cd /d "%%~dp0"
    echo "BroostWebServer.exe"
) > "dist\BroostPOS\Launch_BroostWebServer.bat"
echo       Done.

rem Step 7: Compile Installer with Inno Setup
echo [7/7] Compiling installer package...

rem Find ISCC.exe
set "ISCC_PATH=iscc.exe"
if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
)

rem Run compiler
"%ISCC_PATH%" setup.iss
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to compile installer.
    pause
    exit /b 1
)
echo       Done.

echo.
echo =====================================================
echo              BUILD COMPLETED SUCCESSFULLY!
echo =====================================================
echo.
echo  App folder  :  dist\BroostPOS\
echo  Installer   :  CashierSystem_Setup.exe
echo  Local site  :  http://127.0.0.1:8765
echo  Admin panel :  http://127.0.0.1:8765/admin
echo =====================================================
pause
