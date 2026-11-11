@echo off
setlocal
cd /d "%~dp0"
title ORI 3.5.0
set PYTHONUTF8=1

if not exist ".venv\Scripts\python.exe" (
    echo ORI's virtual environment is missing.
    echo Run setup_ori.bat first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" main.py
if errorlevel 1 (
    echo.
    echo ORI stopped with an error. Keep this window open and copy the error details when asking for help.
    pause
)
