param()

$TaskName = "Codex Team Skills Auto Update"
$InstallRoot = if ($env:CODEX_TEAM_SKILLS_HOME) { $env:CODEX_TEAM_SKILLS_HOME } else { Join-Path $env:LOCALAPPDATA "CodexTeamSkills" }
$StatePath = Join-Path $InstallRoot "state\state.json"
$PluginDest = if ($env:CODEX_TEAM_SKILLS_PLUGIN_DIR) { $env:CODEX_TEAM_SKILLS_PLUGIN_DIR } else { Join-Path $HOME "plugins\team-skills" }
$MarketplacePath = if ($env:CODEX_TEAM_SKILLS_MARKETPLACE) { $env:CODEX_TEAM_SKILLS_MARKETPLACE } else { Join-Path $HOME ".agents\plugins\marketplace.json" }

Write-Host "[team-skills] Plugin path: $PluginDest"
Write-Host "[team-skills] Plugin установлен: $(Test-Path (Join-Path $PluginDest '.codex-plugin\plugin.json'))"
Write-Host "[team-skills] Marketplace: $MarketplacePath"

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Write-Host "[team-skills] Автообновление включено: $([bool]$task)"

if (Test-Path $StatePath) {
    Write-Host "[team-skills] Последнее успешное обновление:"
    Get-Content $StatePath
} else {
    Write-Host "[team-skills] Ещё нет записи о успешном обновлении."
}
