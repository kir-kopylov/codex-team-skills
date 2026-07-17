param(
    [string]$ManifestUrl = $env:CODEX_TEAM_SKILLS_MANIFEST_URL,
    [string]$LatestUrl = $env:CODEX_TEAM_SKILLS_LATEST_URL,
    [switch]$RepairInstall,
    [switch]$ValidateOnly,
    [switch]$VerifySignatureOnly,
    [string]$PayloadPath,
    [string]$SignaturePath
)

$ErrorActionPreference = "Stop"

$UpdaterVersion = "1.1.0"
$PluginName = "team-skills"
$MarketplaceName = "codex-team-skills"
$RepoReleaseBase = "https://github.com/kir-kopylov/codex-team-skills/releases/latest/download"
$InstallRoot = if ($env:CODEX_TEAM_SKILLS_HOME) { $env:CODEX_TEAM_SKILLS_HOME } else { Join-Path $env:LOCALAPPDATA "CodexTeamSkills" }
$BinDir = Join-Path $InstallRoot "bin"
$CacheDir = Join-Path $InstallRoot "cache"
$StateDir = Join-Path $InstallRoot "state"
$LogDir = Join-Path $InstallRoot "logs"
$PluginDest = if ($env:CODEX_TEAM_SKILLS_PLUGIN_DIR) { $env:CODEX_TEAM_SKILLS_PLUGIN_DIR } else { Join-Path $HOME "plugins\team-skills" }
$MarketplaceRoot = if ($env:CODEX_TEAM_SKILLS_MARKETPLACE_ROOT) { $env:CODEX_TEAM_SKILLS_MARKETPLACE_ROOT } else { $HOME }
$MarketplacePath = if ($env:CODEX_TEAM_SKILLS_MARKETPLACE) { $env:CODEX_TEAM_SKILLS_MARKETPLACE } else { Join-Path $MarketplaceRoot ".agents\plugins\marketplace.json" }
$CodexConfigPath = if ($env:CODEX_TEAM_SKILLS_CODEX_CONFIG) { $env:CODEX_TEAM_SKILLS_CODEX_CONFIG } else { Join-Path $HOME ".codex\config.toml" }
$CodexPluginCacheDir = if ($env:CODEX_TEAM_SKILLS_CODEX_PLUGIN_CACHE_DIR) { $env:CODEX_TEAM_SKILLS_CODEX_PLUGIN_CACHE_DIR } else { Join-Path $HOME ".codex\plugins\cache\codex-team-skills" }
$PublicKeyPath = if ($env:CODEX_TEAM_SKILLS_PUBLIC_KEY) { $env:CODEX_TEAM_SKILLS_PUBLIC_KEY } else { Join-Path $BinDir "team-skills-public-key.pem" }
# Trust anchor pinned at build time: sha256 of installer/team-skills-public-key.pem.
# Если установленный public key не совпадает с этим значением — это подмена якоря доверия.
$ExpectedPublicKeySha256 = "6303efaa119fef81c5c40a281e85998351aa5c7a81100e00e4921198403371a6"
# Те же public RSA parameters, что в закреплённом PEM. Windows PowerShell 5.1
# не умеет RSA.ImportFromPem, поэтому импортирует параметры через CAPI.
$PinnedPublicKeyModulusBase64 = "5XeHpCkSYFOrpk717iXbEM7Pf7UWajm5zor6C8eX0+wSXq2dOQGk2VKW217gtFLQXtnEmVIeB3VRiU1lmltnOJVpNoLxoayTSiBUYoNUSRrMxb5WqPLLT9LiHk2GtNx/VLhwMJxvbR2cidTcYmnQyNBcsSCEV+BWeY0ExCaRzLAxoh9ulDcdnhEASL7Lp/BrxR6rJz2hRboBgPEVh8bC0ZTv+DGjuF4XJPmBtj3RC8nt307s3sKHIn/rcqK9qY9bUsU4Tp6HarNId7EoaPC6SEvTndy/CjYXcLJp/oLzcy6b0RPRI7qJFX8MhqnvyBdinYZTk2VO6bqGQR0rJkvN2g7eYRhThPHKiIMGXMM8QedZZW6Sqjvk8PjLLupy44VHUn5OH0verJMGe0gkMW664AnY5laFIYMxR+OHD/4cLB+bwwoBYfiZf9o4r4PkIwbzb1KLA0AnXXmEiF/oT8Bgu/mpmFCSPxe3jzoN6UDgQ3g4pr2kV0rbe19+iNbIUItx"
$PinnedPublicKeyExponentBase64 = "AQAB"
$StatePath = Join-Path $StateDir "state.json"
$LogPath = Join-Path $LogDir "team-skills-update.log"
$AllowUnsigned = $env:CODEX_TEAM_SKILLS_ALLOW_UNSIGNED -eq "1"
$Script:InvalidatedCodexPluginCache = ""

if (-not $LatestUrl) {
    $LatestUrl = "$RepoReleaseBase/latest.json"
}

if ($ValidateOnly) {
    Write-Host "[team-skills] ValidateOnly: update-team-skills.ps1 parsed and initialized."
    exit 0
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

function Get-Sha256($Path) {
    return (Get-FileHash -Algorithm SHA256 $Path).Hash.ToLowerInvariant()
}

function Verify-Sha256($Path, $Expected) {
    $actual = Get-Sha256 $Path
    if ($actual -ne $Expected.ToLowerInvariant()) {
        throw "Checksum mismatch для $Path."
    }
}

function Verify-PublicKeyPin() {
    if (-not (Test-Path $PublicKeyPath)) {
        throw "Public key не найден: $PublicKeyPath"
    }
    $actual = (Get-FileHash -Algorithm SHA256 $PublicKeyPath).Hash.ToLowerInvariant()
    if ($actual -ne $ExpectedPublicKeySha256) {
        throw "Public key не совпадает с закреплённым якорем доверия (sha256 mismatch). Возможна подмена ключа подписи. Оставляю текущий рабочий plugin без изменений."
    }
}

function Verify-Signature($PayloadPath, $SignaturePath) {
    if ($AllowUnsigned) {
        Write-Log "ВНИМАНИЕ: проверка подписи ОТКЛЮЧЕНА (CODEX_TEAM_SKILLS_ALLOW_UNSIGNED=1). Это небезопасный режим только для разработки: устанавливается НЕпроверенный код. В обычной работе не используйте."
        return
    }
    Verify-PublicKeyPin

    $rsa = $null
    try {
        $cspParameters = New-Object System.Security.Cryptography.CspParameters
        $cspParameters.ProviderType = 24
        $rsa = New-Object System.Security.Cryptography.RSACryptoServiceProvider -ArgumentList $cspParameters
        $rsa.PersistKeyInCsp = $false

        $rsaParameters = New-Object System.Security.Cryptography.RSAParameters
        $rsaParameters.Modulus = [Convert]::FromBase64String($PinnedPublicKeyModulusBase64)
        $rsaParameters.Exponent = [Convert]::FromBase64String($PinnedPublicKeyExponentBase64)
        $rsa.ImportParameters($rsaParameters)
    } catch {
        if ($rsa) { $rsa.Dispose() }
        throw "Не удалось инициализировать проверку подписи в Windows PowerShell 5.1. Обновление не применено; запустите свежий официальный installer. Причина: $($_.Exception.Message)"
    }

    try {
        $payload = [System.IO.File]::ReadAllBytes($PayloadPath)
        $signature = [System.IO.File]::ReadAllBytes($SignaturePath)
        $sha256Oid = [System.Security.Cryptography.CryptoConfig]::MapNameToOID("SHA256")
        $ok = $rsa.VerifyData($payload, $sha256Oid, $signature)
    } catch {
        throw "Не удалось проверить подпись обновления в Windows PowerShell 5.1. Обновление не применено. Причина: $($_.Exception.Message)"
    } finally {
        if ($rsa) { $rsa.Dispose() }
    }
    if (-not $ok) {
        throw "Подпись обновления недействительна: $PayloadPath. Оставляю текущий рабочий plugin без изменений."
    }
}

function Download-Signed($Url, $Destination) {
    Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Destination
    if ($AllowUnsigned) {
        return
    }
    $signaturePath = "$Destination.sig"
    Invoke-WebRequest -UseBasicParsing -Uri "$Url.sig" -OutFile $signaturePath
    Verify-Signature $Destination $signaturePath
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

function Remove-ManagedCodexBlock($Text) {
    $begin = "# BEGIN codex-team-skills managed block"
    $end = "# END codex-team-skills managed block"
    $targets = @("[marketplaces.codex-team-skills]", '[plugins."team-skills@codex-team-skills"]')
    $lines = @($Text -split "`r?`n")
    $kept = New-Object System.Collections.Generic.List[string]
    $i = 0
    while ($i -lt $lines.Count) {
        $trimmed = $lines[$i].Trim()
        if ($trimmed -eq $begin) {
            $i++
            while ($i -lt $lines.Count -and $lines[$i].Trim() -ne $end) { $i++ }
            $i++
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
    return (($kept -join "`n").TrimEnd() + "`n")
}

function Update-CodexRegistry() {
    $configDir = Split-Path $CodexConfigPath -Parent
    Ensure-Directory $configDir
    $original = if (Test-Path $CodexConfigPath) { Get-Content $CodexConfigPath -Raw } else { "" }
    $next = Remove-ManagedCodexBlock $original
    if ($next.Trim()) {
        $next = $next.TrimEnd() + "`n`n"
    }
    $source = $MarketplaceRoot.Replace("\", "/")
    $now = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $next += @"
# BEGIN codex-team-skills managed block
[marketplaces.codex-team-skills]
last_updated = "$now"
source_type = "local"
source = "$source"

[plugins."team-skills@codex-team-skills"]
enabled = true
# END codex-team-skills managed block
"@

    $backup = $null
    if (Test-Path $CodexConfigPath) {
        $backup = "$CodexConfigPath.codex-team-skills.bak.$((Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ"))"
        Copy-Item $CodexConfigPath $backup -Force
    }
    try {
        Set-Content -Path $CodexConfigPath -Value $next -Encoding UTF8
    } catch {
        if ($backup -and (Test-Path $backup)) {
            Copy-Item $backup $CodexConfigPath -Force
        }
        throw
    }
}

function Invalidate-CodexPluginCache() {
    if ([string]::IsNullOrWhiteSpace($CodexPluginCacheDir)) {
        Write-Log "Codex plugin cache invalidation skipped: empty cache path."
        return
    }
    $fullCachePath = [System.IO.Path]::GetFullPath($CodexPluginCacheDir)
    $pathRoot = [System.IO.Path]::GetPathRoot($fullCachePath)
    if ($fullCachePath -eq $pathRoot -or $fullCachePath -eq [System.IO.Path]::GetFullPath($HOME)) {
        Write-Log "Codex plugin cache invalidation skipped: unsafe cache path: $CodexPluginCacheDir"
        return
    }

    if (-not (Test-Path $CodexPluginCacheDir)) {
        Write-Log "Codex plugin cache already absent: $CodexPluginCacheDir"
        return
    }

    $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $staleDir = "$CodexPluginCacheDir.stale.$stamp.$PID"
    try {
        Move-Item $CodexPluginCacheDir $staleDir -Force
        $Script:InvalidatedCodexPluginCache = $staleDir
        Write-Log "Codex plugin cache invalidated: moved $CodexPluginCacheDir -> $staleDir"
    } catch {
        Remove-Item $CodexPluginCacheDir -Recurse -Force
        $Script:InvalidatedCodexPluginCache = $CodexPluginCacheDir
        Write-Log "Codex plugin cache invalidated: removed $CodexPluginCacheDir"
    }
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

function Install-SupportFiles($SupportDir) {
    Ensure-Directory $BinDir
    foreach ($file in Get-ChildItem $SupportDir -File) {
        $dest = Join-Path $BinDir $file.Name
        if ($file.Name -eq "update-team-skills.ps1") {
            Copy-Item $file.FullName "$dest.next" -Force
            continue
        }
        Copy-Item $file.FullName $dest -Force
    }
}

function Write-State($Manifest, $BundleUrl, $SignatureState) {
    $state = [ordered]@{
        last_success_at = (Get-Date).ToUniversalTime().ToString("o")
        product_version = $Manifest.product_version
        runtime_version = $Manifest.runtime_version
        release_id = $Manifest.release_id
        commit = $Manifest.commit
        channel = $Manifest.channel
        bundle_url = $BundleUrl
        plugin_path = $PluginDest
        marketplace_path = $MarketplacePath
        codex_config_path = $CodexConfigPath
        updater_version = $UpdaterVersion
        signature_verification = $SignatureState
        codex_plugin_cache_path = $CodexPluginCacheDir
        codex_plugin_cache_invalidated_path = $Script:InvalidatedCodexPluginCache
        runtime_visibility = "requires Codex restart after plugin swap and Codex cache invalidation; cannot be proven from shell"
    }
    Ensure-Directory $StateDir
    $state | ConvertTo-Json -Depth 8 | Set-Content -Path $StatePath -Encoding UTF8
}

function Repair-Install() {
    if (-not (Test-Path (Join-Path $PluginDest ".codex-plugin\plugin.json"))) {
        throw "Repair не применён: plugin не найден: $PluginDest"
    }
    Update-Marketplace $PluginDest
    Update-CodexRegistry
    Invalidate-CodexPluginCache
    $pluginManifest = Get-Content (Join-Path $PluginDest ".codex-plugin\plugin.json") -Raw | ConvertFrom-Json
    $manifest = [pscustomobject]@{
        product_version = if ($pluginManifest.product_version) { $pluginManifest.product_version } else { $pluginManifest.version }
        runtime_version = $pluginManifest.version
        release_id = "repair-install"
        commit = ""
        channel = "local"
    }
    Write-State $manifest "" "repair-no-download"
    Write-Log "Repair завершён: Codex registry настроен. Перезапустите Codex."
}

if ($VerifySignatureOnly) {
    if ($AllowUnsigned) {
        Write-Error "VerifySignatureOnly запрещён при CODEX_TEAM_SKILLS_ALLOW_UNSIGNED=1."
        exit 1
    }
    if ([string]::IsNullOrWhiteSpace($PayloadPath) -or [string]::IsNullOrWhiteSpace($SignaturePath)) {
        Write-Error "Для VerifySignatureOnly нужны PayloadPath и SignaturePath."
        exit 1
    }
    try {
        Verify-Signature $PayloadPath $SignaturePath
        Write-Host "[team-skills] Подпись проверена: $PayloadPath"
        exit 0
    } catch {
        Write-Error $_.Exception.Message
        exit 1
    }
}

try {
    Ensure-Directory $CacheDir
    Ensure-Directory $StateDir
    Ensure-Directory $LogDir
    Ensure-Directory $BinDir

    if ($RepairInstall) {
        Repair-Install
        exit 0
    }

    $workDir = Join-Path $CacheDir ("work-" + [guid]::NewGuid().ToString("N"))
    Ensure-Directory $workDir
    $latestPath = Join-Path $workDir "latest.json"
    $manifestPath = Join-Path $workDir "manifest.json"
    $bundlePath = Join-Path $workDir "team-skills-bundle.zip"
    $expandedDir = Join-Path $workDir "expanded"
    $supportDir = Join-Path $workDir "support"
    Ensure-Directory $supportDir

    if (-not $ManifestUrl) {
        Write-Log "Скачиваю signed latest.json."
        Download-Signed $LatestUrl $latestPath
        $latest = Get-Content $latestPath -Raw | ConvertFrom-Json
        $ManifestUrl = $latest.manifest_url
    }

    Write-Log "Скачиваю signed manifest.json."
    Download-Signed $ManifestUrl $manifestPath
    $manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
    $bundleUrl = $manifest.plugin_bundle.url

    Write-Log "Скачиваю plugin bundle."
    Invoke-WebRequest -UseBasicParsing -Uri $bundleUrl -OutFile $bundlePath
    Verify-Sha256 $bundlePath $manifest.plugin_bundle.sha256

    foreach ($entry in @($manifest.support_files)) {
        $dest = Join-Path $supportDir $entry.name
        Invoke-WebRequest -UseBasicParsing -Uri $entry.url -OutFile $dest
        Verify-Sha256 $dest $entry.sha256
    }

    Expand-Archive -Path $bundlePath -DestinationPath $expandedDir -Force
    $pluginRoot = Find-PluginRoot $expandedDir
    $pluginManifest = Get-Content (Join-Path $pluginRoot ".codex-plugin\plugin.json") -Raw | ConvertFrom-Json
    if ($pluginManifest.version -ne $manifest.runtime_version) {
        throw "runtime_version mismatch: plugin=$($pluginManifest.version) manifest=$($manifest.runtime_version)"
    }

    Update-Marketplace $PluginDest
    Update-CodexRegistry
    Swap-Plugin $pluginRoot
    Install-SupportFiles $supportDir
    Invalidate-CodexPluginCache
    Write-State $manifest $bundleUrl "signed"
    Write-Log "Установлена проверенная версия team-skills: product=$($manifest.product_version) runtime=$($manifest.runtime_version) release=$($manifest.release_id)."
    Write-Log "Перезапустите Codex, чтобы он перечитал plugin после cache invalidation; runtime visibility cannot be proven from shell."
} catch {
    Write-Log "Обновление не применено: $($_.Exception.Message)"
    throw
} finally {
    if ($workDir -and (Test-Path $workDir)) {
        Remove-Item $workDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
