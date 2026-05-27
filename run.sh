#!/bin/bash
# Broost POS Desktop - Startup Script
# Created by DevOps automation helper

# Resolve absolute script path directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Verify virtual environment exists
if [ ! -d ".venv" ]; then
    echo "[!] Virtual environment not found. Initialising..."
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install PyQt6
fi

# Ensure database is initialised
if [ ! -f "broost_pos.db" ]; then
    echo "[*] Initialising SQLite database..."
    .venv/bin/python database.py
fi

echo "[*] Launching Broost POS Desktop Application..."
.venv/bin/python app.py
