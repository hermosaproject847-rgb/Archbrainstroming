@echo off
REM ============================================================
REM  ARCH BRAIN STORMING  -  ONLINE (fast + use from anywhere)
REM  Runs the fast local server on THIS PC and opens a free
REM  Cloudflare tunnel so your phone can reach it from ANY
REM  network. Keep this window OPEN while you use the app.
REM ============================================================
title ARCH BRAIN STORMING - Online (Cloudflare Tunnel)
cd /d "%~dp0"

set "PY=%USERPROFILE%\pyembed\python.exe"
if not exist "%PY%" set "PY=python"
set "PORT=8080"
set "MPLBACKEND=Agg"

echo.
echo   Starting the local server on this PC...
start "ABS Web Server" /min cmd /c ""%PY%" webserver.py"
timeout /t 5 >nul

echo.
echo ====================================================================
echo   NEECHE ek link aayega jaise:  https://xxxx.trycloudflare.com
echo   USSE apne PHONE pe kholo (kisi bhi WiFi / mobile data se).
echo.
echo   - Ye window OPEN rehni chahiye jab tak app use kar rahe ho.
echo   - Har baar start karne pe link BADAL jaata hai (naya copy karo).
echo   - Band karne ke liye: is window ko band kar do.
echo ====================================================================
echo.

"%~dp0cloudflared.exe" tunnel --url http://localhost:%PORT% --no-autoupdate

echo.
echo   Stopping local server...
taskkill /FI "WINDOWTITLE eq ABS Web Server*" /T /F >nul 2>&1
echo   Stopped. Press any key to close.
pause >nul
