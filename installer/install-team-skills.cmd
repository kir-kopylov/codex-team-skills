@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "PS_SCRIPT=%SCRIPT_DIR%install-team-skills.ps1"
set "DOWNLOADED_INSTALLER=0"

if not exist "%PS_SCRIPT%" (
  set "PS_SCRIPT=%TEMP%\install-team-skills-%RANDOM%-%RANDOM%.ps1"
  set "DOWNLOADED_INSTALLER=1"
  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $u='https://github.com/kir-kopylov/codex-team-skills/releases/download/__TEAM_SKILLS_RELEASE_TAG__/install-team-skills.ps1'; for($i=1;$i -le 3;$i++){try{Invoke-WebRequest -UseBasicParsing -TimeoutSec 60 -Uri $u -OutFile '!PS_SCRIPT!'; exit 0}catch{Remove-Item -LiteralPath '!PS_SCRIPT!' -Force -ErrorAction SilentlyContinue; if($i -eq 3){exit 1}; Start-Sleep -Seconds $i}}"
  if errorlevel 1 (
    del /f /q "!PS_SCRIPT!" >nul 2>&1
    echo Не удалось скачать PowerShell установщик командных Codex skills.
    exit /b 1
  )
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" %*
set "INSTALL_EXIT_CODE=%ERRORLEVEL%"
if "%DOWNLOADED_INSTALLER%"=="1" del /f /q "%PS_SCRIPT%" >nul 2>&1
exit /b %INSTALL_EXIT_CODE%
