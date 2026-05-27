@echo off
title Broost POS Compiler for Windows
echo ===================================================
echo             Broost POS Windows Compiler
echo ===================================================
echo.

:: Check for Python installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not added to your system PATH.
    echo Please install Python (version 3.10 or higher) and try again.
    pause
    exit /b
)

echo [1/4] Installing and updating dependencies...
pip install --upgrade pip
pip install PyQt6 pyinstaller

echo [2/4] Compiling Broost POS into a single executable...
pyinstaller --noconfirm --onefile --windowed --name "BroostPOS" --clean app.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Compilation failed. Please check the logs above.
    pause
    exit /b
)

echo [3/4] Copying database and assets to dist folder...
if exist broost_pos.db (
    copy broost_pos.db dist\broost_pos.db
) else (
    echo [WARNING] broost_pos.db not found. A blank database will be created dynamically on first launch.
)

echo.
echo ===================================================
echo            COMPILATION COMPLETED SUCCESSFULLY!
echo ===================================================
echo.
echo Your executable is ready at: dist\BroostPOS.exe
echo.
echo Note: The database file (broost_pos.db) has been copied
echo next to the executable in the 'dist' folder. Keep them 
echo together to preserve your store settings and sales.
echo ===================================================
pause
