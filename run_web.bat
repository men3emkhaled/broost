@echo off
cd /d "%~dp0"
python -m pip install -r requirements-web.txt
python run_web.py
