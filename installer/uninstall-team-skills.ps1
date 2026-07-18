param(
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"

$PluginName = "team-skills"
$TaskName = "Codex Team Skills Auto Update"
$LegacyInstallRoot = Join-Path $env:LOCALAPPDATA "CodexTeamSkills"
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

function New-BackupPath($Path) {
    return "$Path.codex-team-skills.bak.$((Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssfffZ"))"
}

function Write-Utf8File($Path, $Text) {
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Text, $encoding)
}

function Remove-ManagedCodexBlock($Text) {
    $begin = "# BEGIN codex-team-skills managed block"
    $end = "# END codex-team-skills managed block"
    $targets = @("[marketplaces.codex-team-skills]", '[plugins."team-skills@codex-team-skills"]')
    $lines = @($Text -split "`r?`n")
    $kept = New-Object System.Collections.Generic.List[string]
    $rescued = New-Object System.Collections.Generic.List[string]
    $index = 0

    while ($index -lt $lines.Count) {
        $trimmed = $lines[$index].Trim()
        if ($trimmed -eq $begin) {
            $index++
            while ($index -lt $lines.Count -and $lines[$index].Trim() -ne $end) {
                $header = $lines[$index].Trim()
                if ($header.StartsWith("[") -and -not ($targets -contains $header)) {
                    $rescued.Add($lines[$index])
                    $index++
                    while (
                        $index -lt $lines.Count -and
                        $lines[$index].Trim() -ne $end -and
                        -not $lines[$index].TrimStart().StartsWith("[")
                    ) {
                        $rescued.Add($lines[$index])
                        $index++
                    }
                } else {
                    $index++
                }
            }
            if ($index -lt $lines.Count) { $index++ }
            continue
        }

        if ($targets -contains $trimmed) {
            $index++
            while ($index -lt $lines.Count -and -not $lines[$index].TrimStart().StartsWith("[")) {
                $index++
            }
            continue
        }

        $kept.Add($lines[$index])
        $index++
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
    $legacyTask = Get-ScheduledTask -TaskPath "\" -TaskName $TaskName -ErrorAction SilentlyContinue
} catch {
    throw "Не удалось проверить старую Scheduled Task: $($_.Exception.Message)"
}
$legacyMarkers = @(
    "bootstrap-team-skills.ps1",
    "update-team-skills.ps1",
    "team-skills-auto-update-with-git-fallback.ps1"
)
$legacyMarkerFound = @(
    $legacyMarkers | Where-Object {
        Test-Path -LiteralPath (Join-Path (Join-Path $LegacyInstallRoot "bin") $_) -PathType Leaf
    }
).Count -gt 0
if ($legacyTask -or $legacyMarkerFound) {
    throw "Сначала запустите remove-team-skills-autoupdate.ps1 -DryRun, затем -Apply. Полный uninstall не удаляет legacy updater."
}

if (Test-Path -LiteralPath $MarketplacePath) {
    $originalBytes = [System.IO.File]::ReadAllBytes($MarketplacePath)
    $data = [System.Text.Encoding]::UTF8.GetString($originalBytes).TrimStart([char]0xFEFF) | ConvertFrom-Json
    if ($data.PSObject.Properties.Name -contains "plugins") {
        $data.plugins = @($data.plugins | Where-Object { $_.name -ne $PluginName })
        $next = $data | ConvertTo-Json -Depth 20
        $backup = New-BackupPath $MarketplacePath
        Copy-Item -LiteralPath $MarketplacePath -Destination $backup -Force
        try {
            Write-Utf8File $MarketplacePath ($next + "`n")
        } catch {
            Copy-Item -LiteralPath $backup -Destination $MarketplacePath -Force
            throw
        }
        Write-Info "Запись team-skills удалена из marketplace."
    }
}

if (Test-Path -LiteralPath $CodexConfigPath) {
    $text = [System.IO.File]::ReadAllText($CodexConfigPath)
    $next = Remove-ManagedCodexBlock $text
    $backup = New-BackupPath $CodexConfigPath
    Copy-Item -LiteralPath $CodexConfigPath -Destination $backup -Force
    try {
        Write-Utf8File $CodexConfigPath $next
    } catch {
        Copy-Item -LiteralPath $backup -Destination $CodexConfigPath -Force
        throw
    }
    Write-Info "Запись team-skills удалена из Codex registry."
}

if (Test-Path -LiteralPath $PluginDest) {
    Assert-SafeRemovalPath $PluginDest
    Remove-Item -LiteralPath $PluginDest -Recurse -Force
    if (Test-Path -LiteralPath $PluginDest) {
        throw "Не удалось удалить локальный plugin team-skills."
    }
    Write-Info "Локальный plugin team-skills удалён."
}

if (Test-Path -LiteralPath $CodexPluginCacheDir) {
    Assert-SafeRemovalPath $CodexPluginCacheDir
    Remove-Item -LiteralPath $CodexPluginCacheDir -Recurse -Force
    if (Test-Path -LiteralPath $CodexPluginCacheDir) {
        throw "Не удалось удалить Codex plugin cache team-skills."
    }
    Write-Info "Codex plugin cache team-skills удалён."
}

Write-Info "Удаление завершено. Перезапустите Codex, чтобы он перечитал список plugin."
