@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title ORI 3.1 Windows EXE Builder

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: .venv is missing. Run setup_ori.bat first.
  pause
  exit /b 1
)

set "PY=.venv\Scripts\python.exe"
echo Installing the Windows executable packager...
"%PY%" -m pip install --upgrade pyinstaller
if errorlevel 1 goto :fail

echo Removing old build output...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM One-folder packaging is intentional: it is easier to diagnose and update than
REM one-file packaging for Qt, audio drivers, dynamic action modules and plugins.
REM Keep the contents beside ORI.exe because ORI resolves writable config relative
REM to the executable directory. Never bundle config/api_keys.json or user memory.
"%PY%" -m PyInstaller --noconfirm --clean --onedir --windowed ^
  --name ORI --contents-directory . ^
  --icon "config\ori.ico" ^
  --add-data "core;core" ^
  --add-data "actions;actions" ^
  --add-data "plugins;plugins" ^
  --add-data "memory;memory" ^
  --add-data "config\ori.ico;config" ^
  --add-data "config\instagram.svg;config" ^
  --add-data "config\api_keys.example.json;config" ^
  --add-data "knowledge;knowledge" ^
  --add-data "dashboard;dashboard" ^
  --collect-all PyQt6 ^
  --collect-all google.genai ^
  --collect-all sounddevice ^
  --collect-all webrtcvad ^
  --collect-all fastapi ^
  --collect-all starlette ^
  --collect-all uvicorn ^
  --collect-all websockets ^
  --collect-all httptools ^
  --collect-all h11 ^
  --collect-all multipart ^
  --collect-all cryptography ^
  --collect-all qrcode ^
  --collect-all PIL ^
  --collect-all pyautogui ^
  --collect-all pyperclip ^
  --collect-all pycaw ^
  --collect-all comtypes ^
  --collect-all mss ^
  --collect-all wmi ^
  --collect-all win32com ^
  --collect-all pynvml ^
  --collect-submodules actions ^
  --collect-submodules core ^
  --collect-submodules plugins ^
  --collect-submodules dashboard ^
  --hidden-import actions ^
  --hidden-import plugins ^
  --hidden-import memory ^
  --hidden-import dashboard.server ^
  --hidden-import uvicorn.logging ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets.auto ^
  --hidden-import uvicorn.lifespan.on ^
  --hidden-import multipart ^
  --hidden-import pythoncom ^
  --hidden-import pywintypes ^
  main.py
if errorlevel 1 goto :fail

if not exist "dist\ORI\ORI.exe" (
  echo ERROR: ORI.exe was not generated.
  goto :fail
)
if not exist "dist\ORI\dashboard\static\app.html" (
  echo ERROR: Phone Remote app.html was not bundled.
  goto :fail
)
if not exist "dist\ORI\dashboard\static\login.html" (
  echo ERROR: Phone Remote login.html was not bundled.
  goto :fail
)
if not exist "dist\ORI\dashboard\static\crypto-js.js" (
  echo ERROR: Phone Remote CryptoJS dependency was not bundled.
  goto :fail
)
if not exist "dist\ORI\dashboard\static\crypto-js-LICENSE.txt" (
  echo ERROR: Phone Remote CryptoJS MIT license was not bundled.
  goto :fail
)
if not exist "dist\ORI\config" mkdir "dist\ORI\config"
if not exist "dist\ORI\config\api_keys.json" (
  copy /y "config\api_keys.example.json" "dist\ORI\config\api_keys.json" >nul
)
if exist "dist\ORI\config\api_keys.json" echo NOTE: Review dist\ORI\config\api_keys.json and enter your own key on first launch.
echo.
echo Build finished. Test dist\ORI\ORI.exe on Windows before sharing it.
echo Keep config\api_keys.json and personal memory out of public releases.
echo This script packages the current implemented code; it does not add missing product features.
pause
exit /b 0

:fail
echo.
echo Build failed. Copy the complete error output before retrying.
pause
exit /b 1
