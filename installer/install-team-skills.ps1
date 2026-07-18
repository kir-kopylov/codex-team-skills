param(
    [string]$ManifestUrl = $env:CODEX_TEAM_SKILLS_MANIFEST_URL,
    [string]$LatestUrl = $env:CODEX_TEAM_SKILLS_LATEST_URL,
    [switch]$ValidateOnly,
    [switch]$VerifySignatureOnly,
    [string]$PayloadPath,
    [string]$SignaturePath
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$PluginName = "team-skills"
$RepoReleaseBase = "https://github.com/kir-kopylov/codex-team-skills/releases/latest/download"
$InstallRoot = if ($env:CODEX_TEAM_SKILLS_HOME) { $env:CODEX_TEAM_SKILLS_HOME } else { Join-Path $env:LOCALAPPDATA "CodexTeamSkills" }
$BinDir = Join-Path $InstallRoot "bin"
$PluginDest = if ($env:CODEX_TEAM_SKILLS_PLUGIN_DIR) { $env:CODEX_TEAM_SKILLS_PLUGIN_DIR } else { Join-Path $HOME "plugins\team-skills" }
$MarketplaceRoot = if ($env:CODEX_TEAM_SKILLS_MARKETPLACE_ROOT) { $env:CODEX_TEAM_SKILLS_MARKETPLACE_ROOT } else { $HOME }
$MarketplacePath = if ($env:CODEX_TEAM_SKILLS_MARKETPLACE) { $env:CODEX_TEAM_SKILLS_MARKETPLACE } else { Join-Path $MarketplaceRoot ".agents\plugins\marketplace.json" }
$CodexConfigPath = if ($env:CODEX_TEAM_SKILLS_CODEX_CONFIG) { $env:CODEX_TEAM_SKILLS_CODEX_CONFIG } else { Join-Path $HOME ".codex\config.toml" }
$CodexPluginCacheDir = if ($env:CODEX_TEAM_SKILLS_CODEX_PLUGIN_CACHE_DIR) { $env:CODEX_TEAM_SKILLS_CODEX_PLUGIN_CACHE_DIR } else { Join-Path $HOME ".codex\plugins\cache\codex-team-skills" }

# Закреплённый public key для Windows PowerShell 5.1. ImportFromPem здесь недоступен,
# поэтому подпись проверяется через совместимые RSA parameters.
$PinnedPublicKeyModulusBase64 = "5XeHpCkSYFOrpk717iXbEM7Pf7UWajm5zor6C8eX0+wSXq2dOQGk2VKW217gtFLQXtnEmVIeB3VRiU1lmltnOJVpNoLxoayTSiBUYoNUSRrMxb5WqPLLT9LiHk2GtNx/VLhwMJxvbR2cidTcYmnQyNBcsSCEV+BWeY0ExCaRzLAxoh9ulDcdnhEASL7Lp/BrxR6rJz2hRboBgPEVh8bC0ZTv+DGjuF4XJPmBtj3RC8nt307s3sKHIn/rcqK9qY9bUsU4Tp6HarNId7EoaPC6SEvTndy/CjYXcLJp/oLzcy6b0RPRI7qJFX8MhqnvyBdinYZTk2VO6bqGQR0rJkvN2g7eYRhThPHKiIMGXMM8QedZZW6Sqjvk8PjLLupy44VHUn5OH0verJMGe0gkMW664AnY5laFIYMxR+OHD/4cLB+bwwoBYfiZf9o4r4PkIwbzb1KLA0AnXXmEiF/oT8Bgu/mpmFCSPxe3jzoN6UDgQ3g4pr2kV0rbe19+iNbIUItx"
$PinnedPublicKeyExponentBase64 = "AQAB"

if (-not $LatestUrl) {
    $LatestUrl = "$RepoReleaseBase/latest.json"
}

function Write-Info($Message) {
    Write-Host "[team-skills] $Message"
}

function Ensure-Directory($Path) {
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Get-Sha256($Path) {
    return (Get-FileHash -Algorithm SHA256 $Path).Hash.ToLowerInvariant()
}

function Verify-Sha256($Path, $Expected) {
    if ((Get-Sha256 $Path) -ne $Expected.ToLowerInvariant()) {
        throw "Checksum mismatch для $(Split-Path $Path -Leaf)."
    }
}

function New-PinnedRsaProvider() {
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
        return $rsa
    } catch {
        if ($rsa) { $rsa.Dispose() }
        throw "Не удалось подготовить проверку подписи в Windows PowerShell 5.1: $($_.Exception.Message)"
    }
}

function Verify-Signature($Payload, $Signature) {
    $rsa = New-PinnedRsaProvider
    try {
        $payloadBytes = [System.IO.File]::ReadAllBytes($Payload)
        $signatureBytes = [System.IO.File]::ReadAllBytes($Signature)
        $sha256Oid = [System.Security.Cryptography.CryptoConfig]::MapNameToOID("SHA256")
        $valid = $rsa.VerifyData($payloadBytes, $sha256Oid, $signatureBytes)
    } finally {
        $rsa.Dispose()
    }
    if (-not $valid) {
        throw "Подпись $(Split-Path $Payload -Leaf) недействительна."
    }
}

function Download-File($Url, $Destination) {
    Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Destination
}

function Download-Signed($Url, $Destination) {
    Download-File $Url $Destination
    $signature = "$Destination.sig"
    Download-File "$Url.sig" $signature
    Verify-Signature $Destination $signature
}

function Update-Marketplace($PluginPath) {
    Ensure-Directory (Split-Path $MarketplacePath -Parent)
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
    $kept = @($data.plugins | Where-Object { $_.name -ne $PluginName })
    $entry = [pscustomobject]@{
        name = $PluginName
        source = [pscustomobject]@{ source = "local"; path = $PluginPath.Replace("\", "/") }
        policy = [pscustomobject]@{ installation = "AVAILABLE"; authentication = "ON_INSTALL" }
        category = "Productivity"
    }
    $data.plugins = @($kept + $entry)
    $data | ConvertTo-Json -Depth 10 | Set-Content -Path $MarketplacePath -Encoding UTF8
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

function Update-CodexRegistry() {
    Ensure-Directory (Split-Path $CodexConfigPath -Parent)
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
    if ([string]::IsNullOrWhiteSpace($CodexPluginCacheDir) -or -not (Test-Path $CodexPluginCacheDir)) {
        return
    }
    $fullPath = [System.IO.Path]::GetFullPath($CodexPluginCacheDir)
    if ($fullPath -eq [System.IO.Path]::GetPathRoot($fullPath) -or $fullPath -eq [System.IO.Path]::GetFullPath($HOME)) {
        throw "Небезопасный путь Codex plugin cache: $CodexPluginCacheDir"
    }
    $stale = "$CodexPluginCacheDir.stale.$((Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')).$PID"
    Move-Item $CodexPluginCacheDir $stale -Force
}

function Find-PluginRoot($ExpandedDir) {
    foreach ($candidate in @(
        (Join-Path $ExpandedDir "team-skills"),
        (Join-Path $ExpandedDir "plugins\team-skills"),
        $ExpandedDir
    )) {
        if (Test-Path (Join-Path $candidate ".codex-plugin\plugin.json")) {
            return $candidate
        }
    }
    throw "В bundle не найден plugin team-skills."
}

function Replace-Plugin($SourceDir) {
    Ensure-Directory (Split-Path $PluginDest -Parent)
    $id = [guid]::NewGuid().ToString("N")
    $temporary = "$PluginDest.tmp.$id"
    $backup = "$PluginDest.previous.$id"
    Copy-Item $SourceDir $temporary -Recurse -Force
    $hadPrevious = Test-Path $PluginDest
    if ($hadPrevious) {
        Move-Item $PluginDest $backup -Force
    }
    try {
        Move-Item $temporary $PluginDest -Force
        if ($hadPrevious -and (Test-Path $backup)) {
            Remove-Item $backup -Recurse -Force
        }
    } catch {
        Remove-Item $PluginDest -Recurse -Force -ErrorAction SilentlyContinue
        if ($hadPrevious -and (Test-Path $backup)) {
            Move-Item $backup $PluginDest -Force
        }
        Remove-Item $temporary -Recurse -Force -ErrorAction SilentlyContinue
        throw
    }
}

function Remove-LegacyUpdater() {
    $cleanupErrors = New-Object System.Collections.Generic.List[string]
    try {
        $task = Get-ScheduledTask -TaskName "Codex Team Skills Auto Update" -ErrorAction SilentlyContinue
        if ($task) {
            Unregister-ScheduledTask -TaskName "Codex Team Skills Auto Update" -Confirm:$false
        }
    } catch {
        $cleanupErrors.Add("Scheduled Task: $($_.Exception.Message)")
    }

    foreach ($name in @(
        "bootstrap-team-skills.ps1",
        "update-team-skills.ps1",
        "update-team-skills.ps1.next",
        "team-skills-status.ps1"
    )) {
        $path = Join-Path $BinDir $name
        if (Test-Path $path) {
            try {
                Remove-Item $path -Force
            } catch {
                $cleanupErrors.Add("$path`: $($_.Exception.Message)")
            }
        }
    }
    foreach ($name in @("cache", "state", "logs")) {
        $path = Join-Path $InstallRoot $name
        if (Test-Path $path) {
            Remove-Item $path -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    try {
        if (Get-ScheduledTask -TaskName "Codex Team Skills Auto Update" -ErrorAction SilentlyContinue) {
            $cleanupErrors.Add("Scheduled Task осталась зарегистрирована")
        }
    } catch {
        $cleanupErrors.Add("не удалось подтвердить удаление Scheduled Task: $($_.Exception.Message)")
    }
    foreach ($name in @(
        "bootstrap-team-skills.ps1",
        "update-team-skills.ps1",
        "update-team-skills.ps1.next",
        "team-skills-status.ps1"
    )) {
        $path = Join-Path $BinDir $name
        if (Test-Path $path) {
            $cleanupErrors.Add("старый файл остался: $path")
        }
    }
    if ($cleanupErrors.Count -gt 0) {
        throw "Не удалось полностью удалить старое автообновление: $($cleanupErrors -join '; ')"
    }
}

if ($ValidateOnly) {
    Write-Info "ValidateOnly: install-team-skills.ps1 parsed and initialized."
    exit 0
}

if ($VerifySignatureOnly) {
    if ([string]::IsNullOrWhiteSpace($PayloadPath) -or [string]::IsNullOrWhiteSpace($SignaturePath)) {
        Write-Error "Для VerifySignatureOnly нужны PayloadPath и SignaturePath."
        exit 1
    }
    try {
        Verify-Signature $PayloadPath $SignaturePath
        Write-Info "Подпись проверена: $PayloadPath"
        exit 0
    } catch {
        Write-Error $_.Exception.Message
        exit 1
    }
}

$workDir = Join-Path ([System.IO.Path]::GetTempPath()) ("codex-team-skills-install-" + [guid]::NewGuid().ToString("N"))
$failed = $false

try {
    Ensure-Directory $workDir
    Remove-LegacyUpdater

    $latestPath = Join-Path $workDir "latest.json"
    $manifestPath = Join-Path $workDir "manifest.json"
    if (-not $ManifestUrl) {
        Write-Info "Скачиваю подписанный указатель release."
        Download-Signed $LatestUrl $latestPath
        $latest = Get-Content $latestPath -Raw | ConvertFrom-Json
        $ManifestUrl = $latest.manifest_url
    }

    Write-Info "Скачиваю подписанный manifest."
    Download-Signed $ManifestUrl $manifestPath
    $manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
    if (-not $manifest.plugin_bundle.url -or -not $manifest.plugin_bundle.sha256) {
        throw "Manifest не содержит plugin bundle."
    }

    $bundlePath = Join-Path $workDir "team-skills-bundle.zip"
    $expandedDir = Join-Path $workDir "expanded"
    Write-Info "Скачиваю plugin bundle."
    Download-File $manifest.plugin_bundle.url $bundlePath
    Verify-Sha256 $bundlePath $manifest.plugin_bundle.sha256
    Expand-Archive -Path $bundlePath -DestinationPath $expandedDir -Force
    $pluginRoot = Find-PluginRoot $expandedDir
    $pluginManifest = Get-Content (Join-Path $pluginRoot ".codex-plugin\plugin.json") -Raw | ConvertFrom-Json
    if ($pluginManifest.version -ne $manifest.runtime_version) {
        throw "runtime_version в bundle не совпадает с manifest."
    }

    $uninstallerEntry = @($manifest.support_files | Where-Object { $_.name -eq "uninstall-team-skills.ps1" }) | Select-Object -First 1
    if (-not $uninstallerEntry) {
        throw "Manifest не содержит Windows uninstaller."
    }
    $uninstallerPath = Join-Path $workDir "uninstall-team-skills.ps1"
    Download-File $uninstallerEntry.url $uninstallerPath
    Verify-Sha256 $uninstallerPath $uninstallerEntry.sha256

    Update-Marketplace $PluginDest
    Update-CodexRegistry
    Replace-Plugin $pluginRoot
    Invalidate-CodexPluginCache

    Ensure-Directory $BinDir
    Copy-Item $uninstallerPath (Join-Path $BinDir "uninstall-team-skills.ps1") -Force

    Write-Info "Установлена проверенная версия team-skills: product=$($manifest.product_version) runtime=$($manifest.runtime_version) release=$($manifest.release_id)."
    Write-Info "Автообновления нет: для новой версии повторно запустите эту же команду установки."
    Write-Info "Перезапустите Codex, чтобы он перечитал plugin."
} catch {
    Write-Error $_.Exception.Message -ErrorAction Continue
    $failed = $true
} finally {
    if (Test-Path $workDir) {
        Remove-Item $workDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

if ($failed) { exit 1 }
exit 0
