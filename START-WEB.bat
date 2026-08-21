@echo off
REM ============================================================
REM  ARCH BRAIN STORMING  -  local web server (fast, offline)
REM  Runs the web UI on THIS PC. Open it in any browser here,
REM  or on your phone over the same Wi-Fi.
REM ============================================================
title ARCH BRAIN STORMING - Web Server
cd /d "%~dp0"

set "PY=%USERPROFILE%\pyembed\python.exe"
if not exist "%PY%" set "PY=python"

set "PORT=8080"
set "MPLBACKEND=Agg"

echo.
echo   Starting ARCH BRAIN STORMING web server...
echo.
echo   On THIS PC, open:      http://localhost:%PORT%
echo.
echo   On your PHONE (same Wi-Fi), open one of these:
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
  for /f "tokens=* delims= " %%b in ("%%a") do echo        http://%%b:%PORT%
)
echo.
echo   (Keep this window OPEN while you use the app. Close it to stop.)
echo ============================================================
echo.

"%PY%" webserver.py

echo.
echo   Server stopped. Press any key to close.
pause >nul
