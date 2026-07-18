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
$CodexPluginCacheDir = if ($env:CODEX_TEAM_SKILLS_CODEX_PLUGIN_CACHE_DIR) { $env:CODEX_TEAM_SKILLS_CODEX_PLUGIN_CACHE_DIR } else { Join-Path $HOME ".codex\plugins\cache\codex-team-skills" }

if ($ValidateOnly) {
    Write-Host "[team-skills] ValidateOnly: uninstall-team-skills.ps1 parsed and initialized."
    exit 0
}

function Write-Info($Message) {
    Write-Host "[team-skills] $Message"
}

function Assert-SafeRemovalPath($Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "Небезопасный пустой путь для удаления."
    }
    $fullPath = [System.IO.Path]::GetFullPath($Path).TrimEnd([char[]]"\/")
    $rootPath = [System.IO.Path]::GetPathRoot($fullPath).TrimEnd([char[]]"\/")
    $homePath = [System.IO.Path]::GetFullPath($HOME).TrimEnd([char[]]"\/")
    if ($fullPath -eq $rootPath -or $fullPath -eq $homePath) {
        throw "Небезопасный путь для удаления: $Path"
    }
}

function Remove-ManagedCodexBlock($Text) {
    $begin = "# BEGIN codex-team-skills managed block"
    $end = "# END codex-team-skills managed block"
    $targets = @("[marketplaces.codex-team-skills]", '[plugins."team-skills@codex-team-skills"]')
    $lines = @($Text -split "`r?`n")
    $kept = New-Object System.Collections.Generic.List[string]
    $rescued = New-Object System.Collections.Generic.List[string]
    $i = 0
    while ($i -lt $lines.Count) {
        $trimmed = $lines[$i].Trim()
        if ($trimmed -eq $begin) {
            $i++
            while ($i -lt $lines.Count -and $lines[$i].Trim() -ne $end) {
                $header = $lines[$i].Trim()
                if ($header.StartsWith("[") -and -not ($targets -contains $header)) {
                    $rescued.Add($lines[$i])
                    $i++
                    while (
                        $i -lt $lines.Count -and
                        $lines[$i].Trim() -ne $end -and
                        -not $lines[$i].TrimStart().StartsWith("[")
                    ) {
                        $rescued.Add($lines[$i])
                        $i++
                    }
                } else {
                    $i++
                }
            }
            if ($i -lt $lines.Count) { $i++ }
            continue
        }
        if ($targets -contains $trimmed) {
            $i++
            while ($i -lt $lines.Count -and -not $lines[$i].TrimStart().StartsWith("[")) { $i++ }
            continue
        }
        $kept.Add($lines[$i])
        $i++
    }
    while ($rescued.Count -gt 0 -and -not $rescued[$rescued.Count - 1].Trim()) {
        $rescued.RemoveAt($rescued.Count - 1)
    }
    if ($rescued.Count -gt 0) {
        if ($kept.Count -gt 0 -and $kept[$kept.Count - 1].Trim()) { $kept.Add("") }
        foreach ($line in $rescued) { $kept.Add($line) }
    }
    return (($kept -join "`n").TrimEnd() + "`n")
}

try {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Info "Старая задача Team Skills удалена из Windows Task Scheduler."
    }
} catch {
    throw "Не удалось удалить старую Scheduled Task: $($_.Exception.Message)"
}
try {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        throw "старая Scheduled Task осталась зарегистрирована"
    }
} catch {
    throw "Не удалось подтвердить удаление старой Scheduled Task: $($_.Exception.Message)"
}

if (Test-Path $PluginDest) {
    Assert-SafeRemovalPath $PluginDest
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
    $text = Get-Content $CodexConfigPath -Raw
    $next = Remove-ManagedCodexBlock $text
    $backup = "$CodexConfigPath.codex-team-skills.bak.$((Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ"))"
    Copy-Item $CodexConfigPath $backup -Force
    try {
        Set-Content -Path $CodexConfigPath -Value $next -Encoding UTF8
    } catch {
        Copy-Item $backup $CodexConfigPath -Force
        throw
    }
    Write-Info "Запись team-skills удалена из Codex registry."
}

if (Test-Path $CodexPluginCacheDir) {
    Assert-SafeRemovalPath $CodexPluginCacheDir
    Remove-Item $CodexPluginCacheDir -Recurse -Force
    Write-Info "Codex plugin cache team-skills удалён."
}

if (Test-Path $InstallRoot) {
    Assert-SafeRemovalPath $InstallRoot
    Remove-Item $InstallRoot -Recurse -Force -ErrorAction Stop
    Write-Info "Локальные служебные файлы Team Skills удалены."
}

Write-Info "Удаление завершено. Перезапустите Codex, чтобы он перечитал список plugin."
