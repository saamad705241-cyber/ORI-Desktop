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
  --collect-submodules actions `
  --collect-submodules core `
  --collect-submodules plugins `
  --hidden-import actions `
  --hidden-import plugins `
  --hidden-import memory `
  --hidden-import webrtcvad `
  main.py

if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

if (!(Test-Path "dist\ORI\ORI.exe")) { throw "Build completed but dist\ORI\ORI.exe is missing." }
if (!(Test-Path "dist\ORI\config")) { New-Item -ItemType Directory -Path "dist\ORI\config" | Out-Null }
if (!(Test-Path "dist\ORI\config\api_keys.json")) {
  Copy-Item "config\api_keys.example.json" "dist\ORI\config\api_keys.json"
}
Write-Host "ORI Windows one-folder package built. User config is created from the example; no personal API key is bundled."
