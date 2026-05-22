param(
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"

$PluginName = "team-skills"
$TaskName = "Codex Team Skills Auto Update"
$InstallRoot = if ($env:CODEX_TEAM_SKILLS_HOME) { $env:CODEX_TEAM_SKILLS_HOME } else { Join-Path $env:LOCALAPPDATA "CodexTeamSkills" }
$PluginDest = if ($env:CODEX_TEAM_SKILLS_PLUGIN_DIR) { $env:CODEX_TEAM_SKILLS_PLUGIN_DIR } else { Join-Path $HOME "plugins\team-skills" }
$MarketplaceRoot = if ($env:CODEX_TEAM_SKILLS_MARKETPLACE_ROOT) { $env:CODEX_TEAM_SKILLS_MARKETPLACE_ROOT } else { $HOME }
$MarketplacePath = if ($env:CODEX_TEAM_SKILLS_MARKETPLACE) { $env:CODEX_TEAM_SKILLS_MARKETPLACE } else { Join-Path $MarketplaceRoot ".agents\plugins\marketplace.json" }
$CodexConfigPath = if ($env:CODEX_TEAM_SKILLS_CODEX_CONFIG) { $env:CODEX_TEAM_SKILLS_CODEX_CONFIG } else { Join-Path $HOME ".codex\config.toml" }

if ($ValidateOnly) {
    Write-Host "[team-skills] ValidateOnly: uninstall-team-skills.ps1 parsed and initialized."
    exit 0
}

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

if (Test-Path $CodexConfigPath) {
    $begin = "# BEGIN codex-team-skills managed block"
    $end = "# END codex-team-skills managed block"
    $text = Get-Content $CodexConfigPath -Raw
    $lines = @($text -split "`r?`n")
    $kept = New-Object System.Collections.Generic.List[string]
    $i = 0
    while ($i -lt $lines.Count) {
        if ($lines[$i].Trim() -eq $begin) {
            $i++
            while ($i -lt $lines.Count -and $lines[$i].Trim() -ne $end) { $i++ }
            $i++
            continue
        }
        $kept.Add($lines[$i])
        $i++
    }
    $backup = "$CodexConfigPath.codex-team-skills.bak.$((Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ"))"
    Copy-Item $CodexConfigPath $backup -Force
    Set-Content -Path $CodexConfigPath -Value (($kept -join "`n").TrimEnd() + "`n") -Encoding UTF8
    Write-Info "Запись team-skills удалена из Codex registry."
}

if (Test-Path $InstallRoot) {
    Remove-Item $InstallRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Info "Удаление завершено. Перезапустите Codex, чтобы он перечитал список plugin."
