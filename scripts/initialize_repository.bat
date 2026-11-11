@echo off
setlocal
cd /d "%~dp0\.."
title ORI Git Repository Setup
where git >nul 2>nul
if errorlevel 1 (
  echo Git was not found. Install Git for Windows, then run this script again.
  pause
  exit /b 1
)
if not exist ".git" (
  git init -b main
  if errorlevel 1 goto :fail
) else (
  echo Git repository already exists.
)
git add .
if errorlevel 1 goto :fail
echo.
echo Repository initialized and safe-to-track files staged.
echo Review with: git status
 echo.
echo Next: create an empty GitHub repository, then run:
echo git remote add origin https://github.com/OWNER/REPOSITORY.git
echo git commit -m "Initial ORI 3.5.0 source"
echo git push -u origin main
 echo.
echo Do not stage config/api_keys.json, config/certs, memory, logs or personal data.
pause
exit /b 0
:fail
echo Repository setup failed. Keep this window open and inspect the error above.
pause
exit /b 1
