@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please create .venv and install requirements.txt first. See README.md.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" main.py
if errorlevel 1 pause
