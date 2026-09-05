@echo off
REM Desktop installer (ARCH-BRAIN-STORMING-Setup.exe) ko AAJ ke code se dobara banata hai.
REM Jab bhi software me change ho aur doosre PC ke liye naya installer chahiye — ye chalao.
cd /d "%~dp0"
"%USERPROFILE%\pyembed\python.exe" installer\build_setup.py
pause
