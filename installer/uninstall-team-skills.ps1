param()

$ErrorActionPreference = "Stop"

$PluginName = "team-skills"
$TaskName = "Codex Team Skills Auto Update"
$InstallRoot = if ($env:CODEX_TEAM_SKILLS_HOME) { $env:CODEX_TEAM_SKILLS_HOME } else { Join-Path $env:LOCALAPPDATA "CodexTeamSkills" }
$PluginDest = if ($env:CODEX_TEAM_SKILLS_PLUGIN_DIR) { $env:CODEX_TEAM_SKILLS_PLUGIN_DIR } else { Join-Path $HOME "plugins\team-skills" }
$MarketplacePath = if ($env:CODEX_TEAM_SKILLS_MARKETPLACE) { $env:CODEX_TEAM_SKILLS_MARKETPLACE } else { Join-Path $HOME ".agents\plugins\marketplace.json" }

function Write-Info($Message) {
    Write-Host "[team-skills] $Message"
}

try {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Info "Автообновление удалено из Windows Task Scheduler."
    }
} catch {
    Write-Info "Не удалось удалить Scheduled Task: $($_.Exception.Message)"
}

if (Test-Path $PluginDest) {
    Remove-Item $PluginDest -Recurse -Force
    Write-Info "Локальный plugin team-skills удалён."
}

if (Test-Path $MarketplacePath) {
    $data = Get-Content $MarketplacePath -Raw | ConvertFrom-Json
    if ($data.PSObject.Properties.Name -contains "plugins") {
        $data.plugins = @($data.plugins | Where-Object { $_.name -ne $PluginName })
        $data | ConvertTo-Json -Depth 10 | Set-Content -Path $MarketplacePath -Encoding UTF8
        Write-Info "Запись team-skills удалена из marketplace."
    }
}

if (Test-Path $InstallRoot) {
    Remove-Item $InstallRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Info "Удаление завершено. Перезапустите Codex, чтобы он перечитал список plugin."
