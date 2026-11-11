@echo off
setlocal
cd /d "%~dp0\.."
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  echo ORI virtual environment not found. Run setup.bat first.
  pause
  exit /b 1
)
"%PY%" -m playwright install chromium firefox
if errorlevel 1 (
  echo Browser runtime installation failed. ORI core features remain available.
  pause
  exit /b 1
)
echo Playwright browser runtime installed.
pause
