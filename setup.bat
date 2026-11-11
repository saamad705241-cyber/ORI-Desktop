@echo off
setlocal
cd /d "%~dp0"
title ORI 3.5.0 Setup
call "%~dp0setup_ori.bat"
exit /b %errorlevel%
