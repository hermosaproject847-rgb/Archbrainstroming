@echo off
REM ============================================================
REM  Code ko Hugging Face Space par push karta hai.
REM  Pehle Space bana lo:  https://huggingface.co/new-space
REM  (name: arch-brain-storming, SDK: Docker, Private)
REM  Push par HF username + Access Token (Write) maangega:
REM  token yahan banta hai: https://huggingface.co/settings/tokens
REM ============================================================
cd /d "%~dp0"
set /p HFUSER=Apna Hugging Face username likho:
if "%HFUSER%"=="" ( echo Username khali hai. & pause & exit /b 1 )
set /p SPACE=Space ka naam [arch-brain-storming]:
if "%SPACE%"=="" set "SPACE=arch-brain-storming"
git remote remove hf >nul 2>&1
git remote add hf "https://huggingface.co/spaces/%HFUSER%/%SPACE%"
echo.
echo   Push ho raha hai -> https://huggingface.co/spaces/%HFUSER%/%SPACE%
echo   (username = %HFUSER%, password = Write token)
echo.
git push hf main --force
if errorlevel 1 (
  echo.
  echo   Push FAIL hua. Token "Write" type ka hai? Space bana hua hai?
) else (
  echo.
  echo   Ho gaya! Space page par build 5-8 min chalega, phir app khulegi:
  echo   https://%HFUSER%-%SPACE%.hf.space
  echo.
  echo   Cloudflare Worker me SPACE_HOST = %HFUSER%-%SPACE%.hf.space
)
pause
