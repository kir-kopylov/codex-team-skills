@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "BAKED_RELEASE_TAG=__TEAM_SKILLS_RELEASE_TAG__"
set "PS_SCRIPT=%TEMP%\install-team-skills-%RANDOM%-%RANDOM%.ps1"

if "%BAKED_RELEASE_TAG:~0,2%"=="__" (
  echo [team-skills] Запущен исходный install-team-skills.cmd без release tag.
  echo TEAM_SKILLS_RESULT=INSTALL_FAILED
  exit /b 1
)

if /I "%~1"=="-ValidateOnly" if "%~2"=="" (
  echo [team-skills] ValidateOnly: install-team-skills.cmd привязан к release.
  echo TEAM_SKILLS_RESULT=VALIDATED
  exit /b 0
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $u='https://github.com/kir-kopylov/codex-team-skills/releases/download/%BAKED_RELEASE_TAG%/install-team-skills.ps1'; for($i=1;$i -le 3;$i++){try{Invoke-WebRequest -UseBasicParsing -TimeoutSec 60 -Uri $u -OutFile '!PS_SCRIPT!'; if(-not (Test-Path -LiteralPath '!PS_SCRIPT!' -PathType Leaf)){throw 'файл не скачан'}; exit 0}catch{Remove-Item -LiteralPath '!PS_SCRIPT!' -Force -ErrorAction SilentlyContinue; if($i -eq 3){exit 1}; Start-Sleep -Seconds $i}}"
if errorlevel 1 (
  del /f /q "!PS_SCRIPT!" >nul 2>&1
  echo [team-skills] Не удалось скачать installer из точного GitHub release.
  echo TEAM_SKILLS_RESULT=INSTALL_FAILED
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" %*
set "INSTALL_EXIT_CODE=%ERRORLEVEL%"
del /f /q "%PS_SCRIPT%" >nul 2>&1
exit /b %INSTALL_EXIT_CODE%
