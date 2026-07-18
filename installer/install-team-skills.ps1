param(
    [string]$ManifestUrl = $env:CODEX_TEAM_SKILLS_MANIFEST_URL,
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$PluginName = "team-skills"
$MarketplaceName = "codex-team-skills"
$BakedReleaseTag = "__TEAM_SKILLS_RELEASE_TAG__"
$PluginDest = if ($env:CODEX_TEAM_SKILLS_PLUGIN_DIR) { $env:CODEX_TEAM_SKILLS_PLUGIN_DIR } else { Join-Path $HOME "plugins\team-skills" }
$MarketplaceRoot = if ($env:CODEX_TEAM_SKILLS_MARKETPLACE_ROOT) { $env:CODEX_TEAM_SKILLS_MARKETPLACE_ROOT } else { $HOME }
$MarketplacePath = if ($env:CODEX_TEAM_SKILLS_MARKETPLACE) { $env:CODEX_TEAM_SKILLS_MARKETPLACE } else { Join-Path $MarketplaceRoot ".agents\plugins\marketplace.json" }
$CodexConfigPath = if ($env:CODEX_TEAM_SKILLS_CODEX_CONFIG) { $env:CODEX_TEAM_SKILLS_CODEX_CONFIG } else { Join-Path $HOME ".codex\config.toml" }
$CodexPluginCacheDir = if ($env:CODEX_TEAM_SKILLS_CODEX_PLUGIN_CACHE_DIR) { $env:CODEX_TEAM_SKILLS_CODEX_PLUGIN_CACHE_DIR } else { Join-Path $HOME ".codex\plugins\cache\$MarketplaceName" }

function Write-Info($Message) {
    Write-Host "[team-skills] $Message"
}

if ($ValidateOnly) {
    Write-Info "ValidateOnly: install-team-skills.ps1 разобран без выполнения установки."
    exit 0
}

if ([string]::IsNullOrWhiteSpace($ManifestUrl)) {
    if ($BakedReleaseTag.StartsWith("__TEAM_SKILLS_")) {
        throw "Запущен исходный installer без release tag. Используйте release-asset."
    }
    $ManifestUrl = "https://github.com/kir-kopylov/codex-team-skills/releases/download/$BakedReleaseTag/manifest.json"
}

function Ensure-Directory($Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Get-ReleaseTagFromManifestUrl($Url) {
    try {
        $uri = [System.Uri]$Url
    } catch {
        throw "Некорректный ManifestUrl."
    }
    if (
        -not $uri.IsAbsoluteUri -or
        $uri.Scheme -ne "https" -or
        $uri.Host -ne "github.com" -or
        -not $uri.IsDefaultPort -or
        $uri.UserInfo -or
        $uri.Query -or
        $uri.Fragment
    ) {
        throw "ManifestUrl должен быть immutable HTTPS URL официального GitHub release."
    }
    $match = [regex]::Match(
        $uri.AbsolutePath,
        "^/kir-kopylov/codex-team-skills/releases/download/(?<tag>team-skills-v[A-Za-z0-9._-]+)/manifest\.json$"
    )
    if (-not $match.Success) {
        throw "ManifestUrl должен указывать на manifest.json конкретного GitHub release."
    }
    return $match.Groups["tag"].Value
}

function Download-File($Url, $Destination) {
    $lastMessage = ""
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Remove-Item -LiteralPath $Destination -Force -ErrorAction SilentlyContinue
            Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Destination -TimeoutSec 60
            if (-not (Test-Path -LiteralPath $Destination -PathType Leaf)) {
                throw "скачанный файл не найден"
            }
            return
        } catch {
            $lastMessage = $_.Exception.Message
            if ($attempt -lt 3) {
                Start-Sleep -Seconds ([math]::Pow(2, $attempt - 1))
            }
        }
    }
    throw "Не удалось скачать release-asset после трёх попыток: $lastMessage"
}

function Get-Sha256($Path) {
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Verify-Sha256($Path, $Expected) {
    if ((Get-Sha256 $Path) -ne $Expected.ToLowerInvariant()) {
        throw "SHA-256 файла $(Split-Path $Path -Leaf) не совпадает с manifest."
    }
}

function Verify-FileSize($Path, $Expected) {
    $actual = (Get-Item -LiteralPath $Path).Length
    if ($actual -ne [int64]$Expected) {
        throw "Размер файла $(Split-Path $Path -Leaf) не совпадает с manifest: ожидалось $Expected, получено $actual."
    }
}

function Assert-SafeManagedPath($Path, $ExpectedLeaf, $Label) {
    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "Пустой путь $Label."
    }
    $fullPath = [System.IO.Path]::GetFullPath($Path).TrimEnd([char[]]"\/")
    $rootPath = [System.IO.Path]::GetPathRoot($fullPath).TrimEnd([char[]]"\/")
    $homePath = [System.IO.Path]::GetFullPath($HOME).TrimEnd([char[]]"\/")
    if ($fullPath -eq $rootPath -or $fullPath -eq $homePath -or (Split-Path $fullPath -Leaf) -ne $ExpectedLeaf) {
        throw "Небезопасный путь $Label`: $Path"
    }
    if (Test-Path -LiteralPath $fullPath) {
        $item = Get-Item -LiteralPath $fullPath -Force
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "$Label не должен быть reparse point: $Path"
        }
    }
    return $fullPath
}

function Write-Utf8NoBomAtomic($Path, $Text) {
    $fullPath = [System.IO.Path]::GetFullPath($Path)
    Ensure-Directory (Split-Path $fullPath -Parent)
    $temporary = "$fullPath.tmp.$PID.$([guid]::NewGuid().ToString('N'))"
    try {
        $encoding = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($temporary, $Text, $encoding)
        if (Test-Path -LiteralPath $fullPath) {
            [System.IO.File]::Replace($temporary, $fullPath, $null)
        } else {
            [System.IO.File]::Move($temporary, $fullPath)
        }
    } finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    }
}

function Save-OptionalFile($Path, $Snapshot) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return $false
    }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Ожидался файл, но найден другой объект: $Path"
    }
    $item = Get-Item -LiteralPath $Path -Force
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Файл не должен быть reparse point: $Path"
    }
    Copy-Item -LiteralPath $Path -Destination $Snapshot -Force
    return $true
}

function Restore-OptionalFile($Path, $Snapshot, $Existed) {
    if ($Existed) {
        Ensure-Directory (Split-Path $Path -Parent)
        Copy-Item -LiteralPath $Snapshot -Destination $Path -Force
    } else {
        Remove-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    }
}

function New-MarketplaceText($OriginalText, $PluginPath) {
    if ([string]::IsNullOrWhiteSpace($OriginalText)) {
        $data = [pscustomobject]@{
            name = "local-team-skills"
            interface = [pscustomobject]@{ displayName = "Локальные командные skills" }
            plugins = @()
        }
    } else {
        try {
            $data = $OriginalText | ConvertFrom-Json
        } catch {
            throw "Marketplace JSON невалиден; установка ничего не изменила: $($_.Exception.Message)"
        }
        if ($null -eq $data -or $data -is [System.Array]) {
            throw "Marketplace JSON должен содержать объект верхнего уровня."
        }
    }
    if (-not ($data.PSObject.Properties.Name -contains "plugins")) {
        $data | Add-Member -MemberType NoteProperty -Name plugins -Value @()
    }
    if (-not ($data.PSObject.Properties.Name -contains "interface")) {
        $data | Add-Member -MemberType NoteProperty -Name interface -Value ([pscustomobject]@{ displayName = "Локальные командные skills" })
    }
    $kept = @($data.plugins | Where-Object { $null -eq $_ -or $_.name -ne $PluginName })
    $entry = [pscustomobject]@{
        name = $PluginName
        source = [pscustomobject]@{ source = "local"; path = $PluginPath.Replace("\", "/") }
        policy = [pscustomobject]@{ installation = "AVAILABLE"; authentication = "ON_INSTALL" }
        category = "Productivity"
    }
    $data.plugins = @($kept + $entry)
    return (($data | ConvertTo-Json -Depth 20) + "`n")
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

function New-CodexConfigText($OriginalText) {
    $next = Remove-ManagedCodexBlock $OriginalText
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
    return ($next.TrimEnd() + "`n")
}

function Assert-MinimalManifest($Manifest, $ExpectedReleaseTag) {
    $expectedTopLevel = @("schema_version", "release_tag", "commit", "plugin_version", "bundle")
    $actualTopLevel = @($Manifest.PSObject.Properties.Name)
    $unexpected = @($actualTopLevel | Where-Object { $expectedTopLevel -notcontains $_ })
    $missing = @($expectedTopLevel | Where-Object { $actualTopLevel -notcontains $_ })
    if ($unexpected.Count -gt 0 -or $missing.Count -gt 0) {
        throw "Manifest не соответствует минимальной schema_version=1."
    }
    if ([int]$Manifest.schema_version -ne 1 -or $Manifest.release_tag -ne $ExpectedReleaseTag) {
        throw "Release tag или schema_version в manifest не совпадает с installer."
    }
    if ($Manifest.commit -notmatch "^[0-9a-fA-F]{7,64}$" -or [string]::IsNullOrWhiteSpace($Manifest.plugin_version)) {
        throw "Manifest содержит некорректные commit или plugin_version."
    }
    $expectedBundle = @("url", "size", "sha256")
    $actualBundle = @($Manifest.bundle.PSObject.Properties.Name)
    if (
        @($actualBundle | Where-Object { $expectedBundle -notcontains $_ }).Count -gt 0 -or
        @($expectedBundle | Where-Object { $actualBundle -notcontains $_ }).Count -gt 0 -or
        $Manifest.bundle.sha256 -notmatch "^[0-9a-fA-F]{64}$" -or
        [int64]$Manifest.bundle.size -le 0
    ) {
        throw "Manifest содержит некорректные метаданные plugin bundle."
    }
}

function Assert-PluginIdentity($PluginRoot, $Manifest) {
    $pluginManifestPath = Join-Path $PluginRoot ".codex-plugin\plugin.json"
    if (-not (Test-Path -LiteralPath $pluginManifestPath -PathType Leaf)) {
        throw "В bundle не найден manifest plugin team-skills."
    }
    $pluginManifest = Get-Content -LiteralPath $pluginManifestPath -Raw | ConvertFrom-Json
    if (
        $pluginManifest.name -ne $PluginName -or
        $pluginManifest.version -ne $Manifest.plugin_version -or
        $pluginManifest.release_tag -ne $Manifest.release_tag -or
        $pluginManifest.commit -ne $Manifest.commit -or
        $pluginManifest.skills -ne "./skills/"
    ) {
        throw "Идентичность plugin в bundle не совпадает с manifest."
    }
}

function Replace-Plugin($StagedPlugin, $Destination, $PreviousPlugin, $HadPlugin) {
    if ($HadPlugin) {
        Move-Item -LiteralPath $Destination -Destination $PreviousPlugin
    }
    try {
        Move-Item -LiteralPath $StagedPlugin -Destination $Destination
    } catch {
        if ($HadPlugin -and (Test-Path -LiteralPath $PreviousPlugin)) {
            Move-Item -LiteralPath $PreviousPlugin -Destination $Destination -Force
        }
        throw
    }
}

function Invalidate-CodexPluginCache($Path) {
    $safePath = Assert-SafeManagedPath $Path $MarketplaceName "Codex plugin cache"
    if (Test-Path -LiteralPath $safePath) {
        Remove-Item -LiteralPath $safePath -Recurse -Force -ErrorAction Stop
    }
}

$workDir = Join-Path ([System.IO.Path]::GetTempPath()) ("codex-team-skills-install-" + [guid]::NewGuid().ToString("N"))
$failed = $false

try {
    Ensure-Directory $workDir
    $expectedReleaseTag = Get-ReleaseTagFromManifestUrl $ManifestUrl
    if (-not $BakedReleaseTag.StartsWith("__TEAM_SKILLS_") -and $expectedReleaseTag -ne $BakedReleaseTag) {
        throw "ManifestUrl не совпадает с release tag, встроенным в installer."
    }
    $releaseBase = "https://github.com/kir-kopylov/codex-team-skills/releases/download/$expectedReleaseTag"

    $manifestPath = Join-Path $workDir "manifest.json"
    Write-Info "Скачиваю manifest конкретного GitHub release."
    Download-File $ManifestUrl $manifestPath
    try {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    } catch {
        throw "Manifest JSON невалиден: $($_.Exception.Message)"
    }
    Assert-MinimalManifest $manifest $expectedReleaseTag
    if ($manifest.bundle.url -ne "$releaseBase/team-skills-bundle.zip") {
        throw "Bundle URL должен указывать на тот же immutable GitHub release, что и installer."
    }

    $bundlePath = Join-Path $workDir "team-skills-bundle.zip"
    $expandedDir = Join-Path $workDir "expanded"
    Write-Info "Скачиваю plugin bundle."
    Download-File $manifest.bundle.url $bundlePath
    Verify-FileSize $bundlePath $manifest.bundle.size
    Verify-Sha256 $bundlePath $manifest.bundle.sha256
    Expand-Archive -LiteralPath $bundlePath -DestinationPath $expandedDir -Force
    $pluginRoot = Join-Path $expandedDir "team-skills"
    Assert-PluginIdentity $pluginRoot $manifest

    $PluginDest = Assert-SafeManagedPath $PluginDest $PluginName "plugin destination"
    $CodexPluginCacheDir = Assert-SafeManagedPath $CodexPluginCacheDir $MarketplaceName "Codex plugin cache"
    if (Test-Path -LiteralPath $PluginDest -PathType Leaf) {
        throw "Plugin destination должен быть каталогом: $PluginDest"
    }
    if (Test-Path -LiteralPath $CodexPluginCacheDir -PathType Leaf) {
        throw "Codex plugin cache должен быть каталогом: $CodexPluginCacheDir"
    }

    $marketplaceSnapshot = Join-Path $workDir "marketplace.original"
    $configSnapshot = Join-Path $workDir "config.original"
    $marketplaceExisted = Save-OptionalFile $MarketplacePath $marketplaceSnapshot
    $configExisted = Save-OptionalFile $CodexConfigPath $configSnapshot
    $marketplaceOriginal = if ($marketplaceExisted) { [System.IO.File]::ReadAllText($marketplaceSnapshot) } else { "" }
    $configOriginal = if ($configExisted) { [System.IO.File]::ReadAllText($configSnapshot) } else { "" }
    $marketplaceNext = New-MarketplaceText $marketplaceOriginal $PluginDest
    $configNext = New-CodexConfigText $configOriginal

    Ensure-Directory (Split-Path $PluginDest -Parent)
    $transactionId = [guid]::NewGuid().ToString("N")
    $stagedPlugin = "$PluginDest.tmp.$transactionId"
    $previousPlugin = "$PluginDest.previous.$transactionId"
    Copy-Item -LiteralPath $pluginRoot -Destination $stagedPlugin -Recurse -Force
    $hadPlugin = Test-Path -LiteralPath $PluginDest
    $pluginActivated = $false
    try {
        Replace-Plugin $stagedPlugin $PluginDest $previousPlugin $hadPlugin
        $pluginActivated = $true
        Write-Utf8NoBomAtomic $MarketplacePath $marketplaceNext
        Write-Utf8NoBomAtomic $CodexConfigPath $configNext
        Assert-PluginIdentity $PluginDest $manifest
        Invalidate-CodexPluginCache $CodexPluginCacheDir
        if ($hadPlugin -and (Test-Path -LiteralPath $previousPlugin)) {
            Remove-Item -LiteralPath $previousPlugin -Recurse -Force -ErrorAction Stop
        }
    } catch {
        $originalError = $_.Exception.Message
        $rollbackErrors = New-Object System.Collections.Generic.List[string]
        if ($pluginActivated) {
            try { Remove-Item -LiteralPath $PluginDest -Recurse -Force -ErrorAction Stop } catch { $rollbackErrors.Add($_.Exception.Message) }
        }
        try {
            if ($hadPlugin -and (Test-Path -LiteralPath $previousPlugin)) {
                Move-Item -LiteralPath $previousPlugin -Destination $PluginDest -Force
            }
        } catch { $rollbackErrors.Add($_.Exception.Message) }
        try { Restore-OptionalFile $MarketplacePath $marketplaceSnapshot $marketplaceExisted } catch { $rollbackErrors.Add($_.Exception.Message) }
        try { Restore-OptionalFile $CodexConfigPath $configSnapshot $configExisted } catch { $rollbackErrors.Add($_.Exception.Message) }
        if ($rollbackErrors.Count -gt 0) {
            throw "Установка не завершена: $originalError Откат также завершился ошибкой: $($rollbackErrors -join '; ')"
        }
        throw "Установка не завершена; прежний plugin и registry восстановлены: $originalError"
    } finally {
        Remove-Item -LiteralPath $stagedPlugin -Recurse -Force -ErrorAction SilentlyContinue
    }

    Write-Info "Установлена версия team-skills $($manifest.plugin_version) из release $($manifest.release_tag)."
    Write-Info "Автообновления нет: для новой версии вручную запустите новый installer."
    Write-Info "Перезапустите Codex, чтобы он перечитал plugin."
} catch {
    Write-Error $_.Exception.Message -ErrorAction Continue
    $failed = $true
} finally {
    if (Test-Path -LiteralPath $workDir) {
        Remove-Item -LiteralPath $workDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

if ($failed) { exit 1 }
exit 0
