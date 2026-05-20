@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PS_SCRIPT=%SCRIPT_DIR%install-team-skills.ps1"

if not exist "%PS_SCRIPT%" (
  set "PS_SCRIPT=%TEMP%\install-team-skills.ps1"
  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/kir-kopylov/codex-team-skills/releases/latest/download/install-team-skills.ps1' -OutFile '%PS_SCRIPT%'"
  if errorlevel 1 (
    echo Не удалось скачать PowerShell установщик командных Codex skills.
    exit /b 1
  )
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" %*
exit /b %ERRORLEVEL%
