param(
    [string[]]$ForwardArgs,
    [switch]$RegisterAutoUpdate,
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
$BootstrapVersion = "1.2.0"
$TaskName = "Codex Team Skills Auto Update"
$InstallRoot = if ($env:CODEX_TEAM_SKILLS_HOME) { $env:CODEX_TEAM_SKILLS_HOME } else { Join-Path $env:LOCALAPPDATA "CodexTeamSkills" }
$BinDir = Join-Path $InstallRoot "bin"
$UpdateScript = Join-Path $BinDir "update-team-skills.ps1"
$NextUpdateScript = "$UpdateScript.next"

if ($ValidateOnly) {
    Write-Host "[team-skills] ValidateOnly: bootstrap-team-skills.ps1 parsed and initialized."
    exit 0
}

function Register-AutoUpdateTask() {
    $triggerTime = Get-Date -Hour 10 -Minute 0 -Second 0
    $action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
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
        -Description "Раз в двое суток запускает проверенное обновление локальных командных Codex skills." `
        -Force | Out-Null

    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    if (-not $task) {
        throw "Scheduled Task не найдена после регистрации."
    }
    Write-Host "[team-skills] Автообновление включено: Windows Task Scheduler, раз в двое суток."
}

if (-not (Test-Path $UpdateScript)) {
    Write-Host "[team-skills] Updater не найден: $UpdateScript"
    Write-Host "[team-skills] Запустите installer заново, чтобы восстановить support files."
    exit 1
}

if ($RegisterAutoUpdate) {
    try {
        Register-AutoUpdateTask
        exit 0
    } catch {
        Write-Error "Не удалось зарегистрировать Scheduled Task '$TaskName': $($_.Exception.Message)"
        exit 1
    }
}

if (Test-Path $NextUpdateScript) {
    Move-Item $NextUpdateScript $UpdateScript -Force
    Write-Host "[team-skills] Updater обновлён из staged .next версии."
}

$env:CODEX_TEAM_SKILLS_BOOTSTRAP_VERSION = $BootstrapVersion
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $UpdateScript @ForwardArgs
exit $LASTEXITCODE
