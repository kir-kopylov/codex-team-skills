param(
    [switch]$ValidateOnly
)

$TaskName = "Codex Team Skills Auto Update"
$InstallRoot = if ($env:CODEX_TEAM_SKILLS_HOME) { $env:CODEX_TEAM_SKILLS_HOME } else { Join-Path $env:LOCALAPPDATA "CodexTeamSkills" }
$BinDir = Join-Path $InstallRoot "bin"
$StatePath = Join-Path $InstallRoot "state\state.json"
$RepairStatePath = Join-Path $InstallRoot "state\last-repair.json"
$FailureStatePath = Join-Path $InstallRoot "state\last-failure.json"
$PluginDest = if ($env:CODEX_TEAM_SKILLS_PLUGIN_DIR) { $env:CODEX_TEAM_SKILLS_PLUGIN_DIR } else { Join-Path $HOME "plugins\team-skills" }
$MarketplaceRoot = if ($env:CODEX_TEAM_SKILLS_MARKETPLACE_ROOT) { $env:CODEX_TEAM_SKILLS_MARKETPLACE_ROOT } else { $HOME }
$MarketplacePath = if ($env:CODEX_TEAM_SKILLS_MARKETPLACE) { $env:CODEX_TEAM_SKILLS_MARKETPLACE } else { Join-Path $MarketplaceRoot ".agents\plugins\marketplace.json" }
$CodexConfigPath = if ($env:CODEX_TEAM_SKILLS_CODEX_CONFIG) { $env:CODEX_TEAM_SKILLS_CODEX_CONFIG } else { Join-Path $HOME ".codex\config.toml" }

if ($ValidateOnly) {
    Write-Host "[team-skills] ValidateOnly: team-skills-status.ps1 parsed and initialized."
    exit 0
}

function Show-StateFile($Path, $Heading, $MissingMessage) {
    if (-not (Test-Path $Path)) {
        Write-Host "[team-skills] $MissingMessage"
        return
    }
    Write-Host "[team-skills] $Heading"
    try {
        Get-Content $Path -ErrorAction Stop
    } catch {
        Write-Host "[team-skills] Не удалось прочитать ${Path}: $($_.Exception.Message)"
    }
}

Write-Host "[team-skills] Plugin path: $PluginDest"
Write-Host "[team-skills] Plugin установлен: $(Test-Path (Join-Path $PluginDest '.codex-plugin\plugin.json'))"
Write-Host "[team-skills] Marketplace: $MarketplacePath"
Write-Host "[team-skills] Codex config: $CodexConfigPath"
if (Test-Path $CodexConfigPath) {
    $config = Get-Content $CodexConfigPath -Raw
    Write-Host "[team-skills] Codex registry managed block: $($config.Contains('# BEGIN codex-team-skills managed block'))"
    Write-Host "[team-skills] Codex marketplace registered: $($config.Contains('[marketplaces.codex-team-skills]'))"
    Write-Host "[team-skills] Codex plugin enabled: $($config.Contains('[plugins."team-skills@codex-team-skills"]'))"
} else {
    Write-Host "[team-skills] Codex registry: config missing"
}

$task = $null
$taskCheck = "unknown"
try {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    $taskCheck = if ($task) { "present" } else { "missing" }
} catch {
    if ($_.FullyQualifiedErrorId -like "CmdletizationQuery_NotFound*") {
        $taskCheck = "missing"
    } else {
        $taskCheck = "failed"
        $taskCheckError = $_.Exception.Message
    }
}

if ($taskCheck -eq "present") {
    Write-Host "[team-skills] Автообновление: включено"
    Write-Host "[team-skills] State: $($task.State)"
    try {
        $taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
        Write-Host "[team-skills] LastRunTime: $($taskInfo.LastRunTime)"
        Write-Host "[team-skills] LastTaskResult: $($taskInfo.LastTaskResult)"
        Write-Host "[team-skills] NextRunTime: $($taskInfo.NextRunTime)"
    } catch {
        Write-Host "[team-skills] LastRunTime: не удалось проверить"
        Write-Host "[team-skills] LastTaskResult: не удалось проверить"
        Write-Host "[team-skills] NextRunTime: не удалось проверить"
    }
} elseif ($taskCheck -eq "missing") {
    Write-Host "[team-skills] Автообновление: отсутствует"
} else {
    Write-Host "[team-skills] Автообновление: не удалось проверить"
    Write-Host "[team-skills] Причина проверки Scheduled Task: $taskCheckError"
}

Show-StateFile $StatePath "Последнее успешное полное обновление:" "Ещё нет записи об успешном полном обновлении."
Show-StateFile $RepairStatePath "Последний успешный repair:" "Ещё нет записи об успешном repair."
Show-StateFile $FailureStatePath "Активная ошибка update/repair:" "Активной ошибки update/repair нет."
Write-Host "[team-skills] Runtime visibility: requires Codex restart; cannot be proven from shell."
