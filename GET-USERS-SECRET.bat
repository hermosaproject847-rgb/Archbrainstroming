@echo off
REM ============================================================
REM  users.json ka content clipboard me copy karta hai.
REM  Ise Hugging Face Space ke Secret  USERS_JSON  me paste karna
REM  hai (restart par bhi clients ke logins bache rahein).
REM ============================================================
set "F=%~dp0users.json"
if not exist "%F%" (
  echo   NOT FOUND: %F%
  pause
  exit /b 1
)
type "%F%" | clip
echo.
echo   Ho gaya! users.json CLIPBOARD me copy ho gaya hai.
echo   Space  Settings ^> Variables and secrets  me naya SECRET:
echo       Name  : USERS_JSON
echo       Value : (Ctrl+V)
echo.
pause
