param(
    [switch]$ValidateOnly
)

$TaskName = "Codex Team Skills Auto Update"
$InstallRoot = if ($env:CODEX_TEAM_SKILLS_HOME) { $env:CODEX_TEAM_SKILLS_HOME } else { Join-Path $env:LOCALAPPDATA "CodexTeamSkills" }
$BinDir = Join-Path $InstallRoot "bin"
$StatePath = Join-Path $InstallRoot "state\state.json"
$PluginDest = if ($env:CODEX_TEAM_SKILLS_PLUGIN_DIR) { $env:CODEX_TEAM_SKILLS_PLUGIN_DIR } else { Join-Path $HOME "plugins\team-skills" }
$MarketplaceRoot = if ($env:CODEX_TEAM_SKILLS_MARKETPLACE_ROOT) { $env:CODEX_TEAM_SKILLS_MARKETPLACE_ROOT } else { $HOME }
$MarketplacePath = if ($env:CODEX_TEAM_SKILLS_MARKETPLACE) { $env:CODEX_TEAM_SKILLS_MARKETPLACE } else { Join-Path $MarketplaceRoot ".agents\plugins\marketplace.json" }
$CodexConfigPath = if ($env:CODEX_TEAM_SKILLS_CODEX_CONFIG) { $env:CODEX_TEAM_SKILLS_CODEX_CONFIG } else { Join-Path $HOME ".codex\config.toml" }

if ($ValidateOnly) {
    Write-Host "[team-skills] ValidateOnly: team-skills-status.ps1 parsed and initialized."
    exit 0
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

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Write-Host "[team-skills] Автообновление включено: $([bool]$task)"

if (Test-Path $StatePath) {
    Write-Host "[team-skills] Последнее успешное обновление:"
    Get-Content $StatePath
} else {
    Write-Host "[team-skills] Ещё нет записи о успешном обновлении."
}
Write-Host "[team-skills] Runtime visibility: requires Codex restart; cannot be proven from shell."
