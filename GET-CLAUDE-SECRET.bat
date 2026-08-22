@echo off
REM ============================================================
REM  Claude CLI ka login-token copy karta hai (clipboard me).
REM  Ise Hugging Face Space ke Secret  CLAUDE_CREDENTIALS  me
REM  paste karna hai. Ye password NAHI hai — ek session token
REM  hai jo sirf aapke Claude account ko CLI me chalata hai.
REM ============================================================
set "F=%USERPROFILE%\.claude\.credentials.json"
if not exist "%F%" (
  echo.
  echo   NOT FOUND: %F%
  echo   Pehle apne PC par Claude CLI me /login karke sign-in karein.
  pause
  exit /b 1
)
type "%F%" | clip
echo.
echo   Ho gaya! Token CLIPBOARD me copy ho gaya hai.
echo.
echo   Ab Hugging Face Space ke  Settings ^> Variables and secrets  me
echo   naya SECRET banayein:
echo       Name  : CLAUDE_CREDENTIALS
echo       Value : (yahan Ctrl+V se paste karein)
echo.
pause
