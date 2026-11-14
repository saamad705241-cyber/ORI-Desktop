$ErrorActionPreference = "Stop"

if (Test-Path "build") { Remove-Item "build" -Recurse -Force }
if (Test-Path "dist") { Remove-Item "dist" -Recurse -Force }

python -m PyInstaller --noconfirm --clean --onedir --windowed `
  --name ORI --contents-directory . `
  --icon "config\ori.ico" `
  --add-data "core;core" `
  --add-data "actions;actions" `
  --add-data "plugins;plugins" `
  --add-data "memory;memory" `
  --add-data "dashboard;dashboard" `
  --add-data "knowledge;knowledge" `
  --add-data "config\ori.ico;config" `
  --add-data "config\instagram.svg;config" `
  --add-data "config\microphone-on.svg;config" `
  --add-data "config\microphone-muted.svg;config" `
  --add-data "config\voice-stop.svg;config" `
  --add-data "config\api_keys.example.json;config" `
  --add-data "LICENSE;." `
  --add-data "ATTRIBUTION.md;." `
  --add-data "THIRD_PARTY_LICENSES.md;." `
  --add-data "UPSTREAM_MARK_LV_README.md;." `
  --add-data "TERMS_AND_CONDITIONS.md;." `
  --collect-all PyQt6 `
  --collect-all google.genai `
  --collect-all sounddevice `
  --collect-all webrtcvad `
  --collect-all fastapi `
  --collect-all starlette `
  --collect-all uvicorn `
  --collect-all websockets `
  --collect-all httptools `
  --collect-all h11 `
  --collect-all multipart `
  --collect-all cryptography `
  --collect-all qrcode `
  --collect-all PIL `
  --collect-all pyautogui `
  --collect-all pyperclip `
  --collect-all pycaw `
  --collect-all comtypes `
  --collect-all mss `
  --collect-all wmi `
  --collect-all win32com `
  --collect-all pynvml `
  --collect-all winrt.windows.devices.geolocation `
  --collect-all winrt.windows.foundation `
  --collect-all winrt.windows.foundation.collections `
  --hidden-import winrt.windows.devices.geolocation `
  --hidden-import winrt.windows.foundation `
  --hidden-import winrt.windows.foundation.collections `
  --hidden-import winrt.system `
  --collect-submodules actions `
  --collect-submodules core `
  --collect-submodules plugins `
  --collect-submodules dashboard `
  --hidden-import actions `
  --hidden-import plugins `
  --hidden-import memory `
  --hidden-import dashboard.server `
  --hidden-import uvicorn.logging `
  --hidden-import uvicorn.loops.auto `
  --hidden-import uvicorn.protocols.http.auto `
  --hidden-import uvicorn.protocols.websockets.auto `
  --hidden-import uvicorn.lifespan.on `
  --hidden-import multipart `
  --hidden-import pythoncom `
  --hidden-import pywintypes `
  --hidden-import webrtcvad `
  main.py

if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

if (!(Test-Path "dist\ORI\ORI.exe")) { throw "Build completed but dist\ORI\ORI.exe is missing." }
foreach ($asset in @("dashboard\static\app.html", "dashboard\static\login.html", "dashboard\static\crypto-js.js", "dashboard\static\crypto-js-LICENSE.txt")) {
  if (!(Test-Path (Join-Path "dist\ORI" $asset))) {
    throw "Build is missing required Phone Remote asset: $asset"
  }
}
if (!(Test-Path "dist\ORI\config")) { throw "Packaged UI asset directory is missing." }
foreach ($helper in @("core\install_update.ps1", "core\update_assistant.ps1", "core\uninstall_launcher.ps1", "core\app_updater.py", "core\app_paths.py")) {
  if (!(Test-Path (Join-Path "dist\ORI" $helper))) {
    throw "Windows package is missing required installer/runtime file: $helper"
  }
}
if (Test-Path "dist\ORI\config\api_keys.json") {
  throw "A live config file must never be included in the installer package."
}
Write-Host "ORI Windows one-folder payload built. Python and application dependencies are bundled; per-user config is created on first launch."
