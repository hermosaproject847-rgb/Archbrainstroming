@echo off
rem Debug launcher — runs the app with a CONSOLE so any start-up error is
rem visible. Use this if the normal shortcut shows nothing.
cd /d "%~dp0"
echo Starting ARCH BRAIN STORMING (debug console)...
echo.
"%~dp0python\python.exe" "app.py"
echo.
echo ============================================================
echo The app window has closed (or failed to start).
echo If you see a Python error above, copy it and send it over.
echo ============================================================
pause
