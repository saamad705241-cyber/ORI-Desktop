@echo off
setlocal
cd /d "%~dp0"
title ORI 3.5.0 Setup

set "PYLAUNCHER="
where py >nul 2>nul
if not errorlevel 1 (
    py -3.12 --version >nul 2>nul
    if not errorlevel 1 set "PYLAUNCHER=py -3.12"
    if not defined PYLAUNCHER (
        py -3.13 --version >nul 2>nul
        if not errorlevel 1 set "PYLAUNCHER=py -3.13"
    )
)

if not defined PYLAUNCHER (
    echo ORI requires Python 3.12 or 3.13 for the supported install path.
    echo Install Python 3.12 from https://www.python.org/downloads/ and enable the Python launcher.
    echo Then run setup_ori.bat again.
    pause
    exit /b 1
)

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3,12),(3,13)) else 1)" >nul 2>nul
    if errorlevel 1 (
        echo Recreating .venv because it uses an unsupported Python version...
        rmdir /s /q ".venv"
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating the project virtual environment...
    %PYLAUNCHER% -m venv .venv
    if errorlevel 1 goto :fail
)

echo Updating pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :fail

echo Installing ORI dependencies. This may take a while and needs internet access...
".venv\Scripts\python.exe" setup.py
if errorlevel 1 goto :fail

echo.
echo ORI 3.5.0 setup complete.
echo ORI uses Google Gemini Live as its primary voice runtime.
echo Start ORI with run.bat. First launch: Continue as a Guest, set your profile, then verify a Google AI Studio API key.
echo Get a key from https://aistudio.google.com/app/apikey
pause
exit /b 0

:fail
echo.
echo Setup failed. Read the error above. Confirm Python 3.12 or 3.13 is installed and try again.
pause
exit /b 1
