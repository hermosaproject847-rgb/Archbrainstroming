@echo off
REM ============================================================
REM  Stop the silent background server + tunnel (started by
REM  run-silent.vbs / at login). Use this when you want the app
REM  offline. It starts again automatically at the next login.
REM ============================================================
title Stop ARCH BRAIN STORMING background

echo Stopping the Cloudflare tunnel...
taskkill /IM cloudflared.exe /F >nul 2>&1

echo Stopping the web server...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*webserver.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo.
echo Done - the app at https://saradigitalstudios.com is now OFFLINE.
echo (It will start again automatically the next time you log in,
echo  or run run-silent.vbs to start it again now.)
echo.
timeout /t 4 >nul
