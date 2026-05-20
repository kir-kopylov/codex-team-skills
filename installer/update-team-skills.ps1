param(
    [string]$ManifestUrl = $env:CODEX_TEAM_SKILLS_MANIFEST_URL
)

$ErrorActionPreference = "Stop"

$PluginName = "team-skills"
$RepoReleaseBase = "https://github.com/kir-kopylov/codex-team-skills/releases/latest/download"
$InstallRoot = if ($env:CODEX_TEAM_SKILLS_HOME) { $env:CODEX_TEAM_SKILLS_HOME } else { Join-Path $env:LOCALAPPDATA "CodexTeamSkills" }
$CacheDir = Join-Path $InstallRoot "cache"
$StateDir = Join-Path $InstallRoot "state"
$LogDir = Join-Path $InstallRoot "logs"
$PluginDest = if ($env:CODEX_TEAM_SKILLS_PLUGIN_DIR) { $env:CODEX_TEAM_SKILLS_PLUGIN_DIR } else { Join-Path $HOME "plugins\team-skills" }
$MarketplacePath = if ($env:CODEX_TEAM_SKILLS_MARKETPLACE) { $env:CODEX_TEAM_SKILLS_MARKETPLACE } else { Join-Path $HOME ".agents\plugins\marketplace.json" }
$StatePath = Join-Path $StateDir "state.json"
$LogPath = Join-Path $LogDir "team-skills-update.log"

if (-not $ManifestUrl) {
    $ManifestUrl = "$RepoReleaseBase/manifest.json"
}

function Ensure-Directory($Path) {
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Write-Log($Message) {
    Ensure-Directory $LogDir
    $line = "{0} {1}" -f (Get-Date).ToUniversalTime().ToString("o"), $Message
    Add-Content -Path $LogPath -Value $line -Encoding UTF8
    Write-Host "[team-skills] $Message"
}

function Update-Marketplace($PluginPath) {
    $marketplaceDir = Split-Path $MarketplacePath -Parent
    Ensure-Directory $marketplaceDir

    if (Test-Path $MarketplacePath) {
        $data = Get-Content $MarketplacePath -Raw | ConvertFrom-Json
    } else {
        $data = [pscustomobject]@{
            name = "local-team-skills"
            interface = [pscustomobject]@{ displayName = "Локальные командные skills" }
            plugins = @()
        }
    }

    if (-not ($data.PSObject.Properties.Name -contains "plugins")) {
        $data | Add-Member -MemberType NoteProperty -Name plugins -Value @()
    }
    if (-not ($data.PSObject.Properties.Name -contains "interface")) {
        $data | Add-Member -MemberType NoteProperty -Name interface -Value ([pscustomobject]@{ displayName = "Локальные командные skills" })
    }

    $keptPlugins = @($data.plugins | Where-Object { $_.name -ne $PluginName })
    $entry = [pscustomobject]@{
        name = $PluginName
        source = [pscustomobject]@{
            source = "local"
            path = $PluginPath.Replace("\", "/")
        }
        policy = [pscustomobject]@{
            installation = "AVAILABLE"
            authentication = "ON_INSTALL"
        }
        category = "Productivity"
    }
    $data.plugins = @($keptPlugins + $entry)
    $data | ConvertTo-Json -Depth 10 | Set-Content -Path $MarketplacePath -Encoding UTF8
}

function Find-PluginRoot($ExpandedDir) {
    $candidates = @(
        (Join-Path $ExpandedDir "team-skills"),
        (Join-Path $ExpandedDir "plugins\team-skills"),
        $ExpandedDir
    )
    foreach ($candidate in $candidates) {
        if (Test-Path (Join-Path $candidate ".codex-plugin\plugin.json")) {
            return $candidate
        }
    }
    throw "В bundle не найден .codex-plugin/plugin.json для team-skills."
}

function Swap-Plugin($SourceDir) {
    $destParent = Split-Path $PluginDest -Parent
    Ensure-Directory $destParent

    $tmpDest = "$PluginDest.tmp.$PID"
    $backupDest = "$PluginDest.previous"
    if (Test-Path $tmpDest) { Remove-Item $tmpDest -Recurse -Force }
    if (Test-Path $backupDest) { Remove-Item $backupDest -Recurse -Force }

    Copy-Item $SourceDir $tmpDest -Recurse -Force

    try {
        if (Test-Path $PluginDest) {
            Move-Item $PluginDest $backupDest -Force
        }
        Move-Item $tmpDest $PluginDest -Force
        if (Test-Path $backupDest) { Remove-Item $backupDest -Recurse -Force }
    } catch {
        if (Test-Path $PluginDest) { Remove-Item $PluginDest -Recurse -Force }
        if (Test-Path $backupDest) { Move-Item $backupDest $PluginDest -Force }
        if (Test-Path $tmpDest) { Remove-Item $tmpDest -Recurse -Force }
        throw
    }
}

Ensure-Directory $CacheDir
Ensure-Directory $StateDir
Ensure-Directory $LogDir

$workDir = Join-Path $CacheDir ("work-" + [guid]::NewGuid().ToString("N"))
Ensure-Directory $workDir

try {
    $manifestPath = Join-Path $workDir "manifest.json"
    $bundlePath = Join-Path $workDir "team-skills-bundle.zip"
    $expandedDir = Join-Path $workDir "expanded"

    Write-Log "Скачиваю manifest проверенного release-bundle."
    Invoke-WebRequest -UseBasicParsing -Uri $ManifestUrl -OutFile $manifestPath
    $manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
    $bundleUrl = if ($manifest.bundle_url) { $manifest.bundle_url } else { "$RepoReleaseBase/team-skills-bundle.zip" }

    if (-not $manifest.sha256) {
        throw "В manifest.json нет sha256 для проверки bundle."
    }

    Write-Log "Скачиваю team-skills-bundle.zip."
    Invoke-WebRequest -UseBasicParsing -Uri $bundleUrl -OutFile $bundlePath
    $actualHash = (Get-FileHash -Algorithm SHA256 $bundlePath).Hash.ToLowerInvariant()
    if ($actualHash -ne $manifest.sha256.ToLowerInvariant()) {
        throw "Checksum mismatch: ожидалось $($manifest.sha256), получено $actualHash."
    }

    Expand-Archive -Path $bundlePath -DestinationPath $expandedDir -Force
    $pluginRoot = Find-PluginRoot $expandedDir
    Swap-Plugin $pluginRoot
    Update-Marketplace $PluginDest

    $state = [ordered]@{
        last_success_at = (Get-Date).ToUniversalTime().ToString("o")
        version = $manifest.version
        commit = $manifest.commit
        sha256 = $manifest.sha256
        plugin_path = $PluginDest
        marketplace_path = $MarketplacePath
        bundle_url = $bundleUrl
    }
    $state | ConvertTo-Json -Depth 5 | Set-Content -Path $StatePath -Encoding UTF8
    Write-Log "Установлена проверенная версия team-skills: version=$($manifest.version), commit=$($manifest.commit)."
} catch {
    Write-Log "Обновление не применено: $($_.Exception.Message)"
    throw
} finally {
    if (Test-Path $workDir) {
        Remove-Item $workDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
