@echo off
REM ============================================================
REM  ONE-TIME SETUP - link saradigitalstudios.com to this app.
REM  Run this ONCE. After that use START-DOMAIN.bat every day.
REM ============================================================
title ARCH BRAIN STORMING - Domain Setup (run once)
cd /d "%~dp0"

set "CF=%~dp0cloudflared.exe"
set "TUNNEL=archbrainstorming"
set "DOMAIN=saradigitalstudios.com"

echo.
echo  ============================================================
echo   STEP 1 of 3 : LOGIN
echo  ------------------------------------------------------------
echo   A browser window will open. LOG IN with the Cloudflare
echo   account that OWNS %DOMAIN% (the one you bought it on),
echo   then click your domain to AUTHORIZE it.
echo  ============================================================
echo.
pause
"%CF%" tunnel login
if errorlevel 1 goto :err

echo.
echo  STEP 2 of 3 : creating the tunnel "%TUNNEL%" ...
"%CF%" tunnel create %TUNNEL%
REM (if it says "already exists", that is fine - carry on)

echo.
echo  STEP 3 of 3 : pointing %DOMAIN% at this tunnel ...
"%CF%" tunnel route dns --overwrite-dns %TUNNEL% %DOMAIN%
if errorlevel 1 goto :err

echo.
echo  ============================================================
echo   DONE!  Setup complete.
echo   From now on: double-click START-DOMAIN.bat and your app
echo   is live at   https://%DOMAIN%
echo  ============================================================
echo.
pause
exit /b 0

:err
echo.
echo  Something went wrong above. Read the message, fix it, and
echo  run SETUP-DOMAIN.bat again. (Most common: logged into the
echo  wrong Cloudflare account - use the one that owns %DOMAIN%.)
echo.
pause
exit /b 1
