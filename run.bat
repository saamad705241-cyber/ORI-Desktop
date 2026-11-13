@echo off
setlocal
cd /d "%~dp0"
title ORI 3.5.4
call "%~dp0run_ori.bat"
exit /b %errorlevel%
