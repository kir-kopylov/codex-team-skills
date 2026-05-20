param(
    [switch]$SkipSchedule,
    [string]$ManifestUrl = $env:CODEX_TEAM_SKILLS_MANIFEST_URL
)

$ErrorActionPreference = "Stop"

$RepoReleaseBase = "https://github.com/kir-kopylov/codex-team-skills/releases/latest/download"
$TaskName = "Codex Team Skills Auto Update"
$InstallRoot = if ($env:CODEX_TEAM_SKILLS_HOME) { $env:CODEX_TEAM_SKILLS_HOME } else { Join-Path $env:LOCALAPPDATA "CodexTeamSkills" }
$BinDir = Join-Path $InstallRoot "bin"
$LogDir = Join-Path $InstallRoot "logs"
$UpdateScript = Join-Path $BinDir "update-team-skills.ps1"

if (-not $ManifestUrl) {
    $ManifestUrl = "$RepoReleaseBase/manifest.json"
}

function Write-Info($Message) {
    Write-Host "[team-skills] $Message"
}

function Ensure-Directory($Path) {
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Install-SupportFile($Name) {
    $source = Join-Path $PSScriptRoot $Name
    $dest = Join-Path $BinDir $Name
    if (Test-Path $source) {
        Copy-Item $source $dest -Force
        return
    }

    $url = "$RepoReleaseBase/$Name"
    Write-Info "Скачиваю служебный файл $Name"
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $dest
}

function Register-AutoUpdateTask() {
    if ($SkipSchedule) {
        Write-Info "Автообновление пропущено по параметру SkipSchedule."
        return
    }

    $triggerTime = Get-Date -Hour 10 -Minute 0 -Second 0
    $action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$UpdateScript`""
    $trigger = New-ScheduledTaskTrigger -Daily -DaysInterval 2 -At $triggerTime
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description "Раз в двое суток обновляет локальные командные Codex skills из проверенного release-bundle." `
        -Force | Out-Null

    Write-Info "Автообновление включено: Windows Task Scheduler, раз в двое суток."
}

Ensure-Directory $InstallRoot
Ensure-Directory $BinDir
Ensure-Directory $LogDir

Install-SupportFile "update-team-skills.ps1"
Install-SupportFile "uninstall-team-skills.ps1"
Install-SupportFile "team-skills-status.ps1"

Write-Info "Ставлю последнюю проверенную версию командных Codex skills."
& $UpdateScript -ManifestUrl $ManifestUrl

Register-AutoUpdateTask

Write-Info "Готово. Перезапустите Codex, чтобы он перечитал plugin team-skills."
Write-Info "Проверка статуса: powershell -NoProfile -ExecutionPolicy Bypass -File `"$BinDir\team-skills-status.ps1`""
