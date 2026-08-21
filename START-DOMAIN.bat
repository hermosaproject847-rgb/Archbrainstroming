@echo off
REM ============================================================
REM  ARCH BRAIN STORMING - live at your own domain (fixed link)
REM  Runs the fast local server + the named Cloudflare tunnel so
REM  the app always opens at https://saradigitalstudios.com
REM  (Run SETUP-DOMAIN.bat ONCE first.)  Keep this window OPEN.
REM ============================================================
title ARCH BRAIN STORMING - saradigitalstudios.com
cd /d "%~dp0"

set "PY=%USERPROFILE%\pyembed\python.exe"
if not exist "%PY%" set "PY=python"
set "PORT=8080"
set "MPLBACKEND=Agg"
set "CF=%~dp0cloudflared.exe"
set "TUNNEL=archbrainstorming"
set "DOMAIN=saradigitalstudios.com"

echo.
echo   Starting the local server on this PC...
start "ABS Web Server" /min cmd /c ""%PY%" webserver.py"
timeout /t 5 >nul

echo.
echo ====================================================================
echo   Your app is LIVE at:    https://%DOMAIN%
echo.
echo   Open that on any phone / PC, from anywhere. It is the SAME link
echo   every time. Keep this window OPEN while you use the app; PC must
echo   stay on and connected to the internet.
echo ====================================================================
echo.

"%CF%" tunnel run --url http://localhost:%PORT% %TUNNEL%

echo.
echo   Stopping local server...
taskkill /FI "WINDOWTITLE eq ABS Web Server*" /T /F >nul 2>&1
echo   Stopped. Press any key to close.
pause >nul
