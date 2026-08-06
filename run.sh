#!/bin/bash
# Broost POS Desktop - Startup Script
# Created by DevOps automation helper

# Resolve absolute script path directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# On Linux, create/use the virtualenv in the home directory to avoid VFAT filesystem limitations (lack of symlinks, etc.)
VENV_PATH="$HOME/.broost_venv"

if [ ! -d "$VENV_PATH" ]; then
    echo "[!] Virtual environment not found at $VENV_PATH. Initialising..."
    python3 -m venv "$VENV_PATH"
    "$VENV_PATH/bin/pip" install --upgrade pip
    "$VENV_PATH/bin/pip" install PyQt6
fi

# Ensure database is initialised
if [ ! -f "broost_pos.db" ]; then
    echo "[*] Initialising SQLite database..."
    "$VENV_PATH/bin/python" database.py
fi

echo "[*] Launching Broost POS Desktop Application..."
"$VENV_PATH/bin/python" app.py
