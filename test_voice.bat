@echo off
setlocal
cd /d "%~dp0"
title ORI Voice Test

if not exist ".venv\Scripts\python.exe" (
    echo ORI's virtual environment is missing. Run setup_ori.bat first.
    pause
    exit /b 1
)

echo Playing a short test using the installed Windows speech voice...
".venv\Scripts\python.exe" -c "import pyttsx3; e=pyttsx3.init('sapi5'); e.say('ORI voice test successful. You should hear this sentence.'); e.runAndWait(); e.stop()"
if errorlevel 1 (
    echo.
    echo Voice test failed. Run setup_ori.bat again and check your Windows sound output device.
    pause
    exit /b 1
)

echo.
echo Voice test command completed. If you heard nothing, check Windows Volume Mixer and the selected output device.
pause
