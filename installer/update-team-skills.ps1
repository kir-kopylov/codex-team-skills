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

$UpdaterVersion = "1.2.0"
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
$FailureStatePath = Join-Path $StateDir "last-failure.json"
$RepairStatePath = Join-Path $StateDir "last-repair.json"
$LogPath = Join-Path $LogDir "team-skills-update.log"
$AllowUnsigned = $env:CODEX_TEAM_SKILLS_ALLOW_UNSIGNED -eq "1"
$Script:InvalidatedCodexPluginCache = ""
$Script:DownloadTimeoutSec = 45
$Script:DownloadMaxAttemptsOverride = $null
$Script:CurrentOperation = if ($RepairInstall) { "repair" } else { "update" }
$Script:CurrentStage = "initialization"
$Script:PluginSwapActive = $false
$Script:PluginBackupPath = ""
$Script:PluginHadPrevious = $false

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

function Write-LogSafe($Message) {
    try {
        Write-Log $Message
    } catch {
        Write-Host "[team-skills] Не удалось записать update-log: $($_.Exception.Message)"
        Write-Host "[team-skills] $Message"
    }
}

function New-TeamSkillsException($Code, $Stage, $Message, [System.Exception]$InnerException = $null) {
    $exception = if ($InnerException) {
        [System.Exception]::new($Message, $InnerException)
    } else {
        [System.Exception]::new($Message)
    }
    $exception.Data["TeamSkillsCode"] = $Code
    $exception.Data["TeamSkillsStage"] = $Stage
    return $exception
}

function Get-TeamSkillsErrorCode([System.Exception]$Exception) {
    if ($Exception -and $Exception.Data.Contains("TeamSkillsCode")) {
        return [string]$Exception.Data["TeamSkillsCode"]
    }
    return "UNKNOWN_FAILURE"
}

function Get-TeamSkillsErrorStage([System.Exception]$Exception) {
    if ($Exception -and $Exception.Data.Contains("TeamSkillsStage")) {
        return [string]$Exception.Data["TeamSkillsStage"]
    }
    return $Script:CurrentStage
}

function Get-SafeFailureMessage($Code) {
    switch ($Code) {
        "SIGNATURE_SETUP_FAILED" { return "Не удалось подготовить совместимую проверку подписи." }
        "SIGNATURE_INVALID" { return "Подпись release metadata недействительна." }
        "DOWNLOAD_FAILED" { return "Не удалось скачать обязательный файл после ограниченного числа попыток." }
        "CHECKSUM_MISMATCH" { return "Контрольная сумма скачанного файла не совпала с manifest." }
        "PLUGIN_MISSING" { return "Локальный plugin не найден; нужен полный официальный installer." }
        "INSTALL_FAILED" { return "Не удалось безопасно завершить установку служебных файлов или plugin." }
        "SCHEDULE_FAILED" { return "Не удалось создать или проверить задачу автообновления." }
        default { return "Операция завершилась неизвестной ошибкой; подробности сохранены в локальном update-log." }
    }
}

function Write-JsonAtomically($Path, $Value) {
    $parent = Split-Path $Path -Parent
    Ensure-Directory $parent
    $tempPath = "$Path.tmp.$PID.$([guid]::NewGuid().ToString('N'))"
    try {
        $Value | ConvertTo-Json -Depth 10 | Set-Content -Path $tempPath -Encoding UTF8
        Move-Item $tempPath $Path -Force
    } finally {
        if (Test-Path $tempPath) {
            Remove-Item $tempPath -Force -ErrorAction SilentlyContinue
        }
    }
}

function Write-FailureState($Code, $Stage) {
    $failure = [ordered]@{
        schema_version = 1
        failed_at = (Get-Date).ToUniversalTime().ToString("o")
        operation = $Script:CurrentOperation
        stage = $Stage
        code = $Code
        message = (Get-SafeFailureMessage $Code)
        updater_version = $UpdaterVersion
    }
    Write-JsonAtomically $FailureStatePath $failure
}

function Clear-FailureState() {
    if (Test-Path $FailureStatePath) {
        Remove-Item $FailureStatePath -Force
    }
}

function Write-ExceptionLog([System.Management.Automation.ErrorRecord]$ErrorRecord, $Code, $Stage) {
    try {
        Ensure-Directory $LogDir
        $stamp = (Get-Date).ToUniversalTime().ToString("o")
        Add-Content -Path $LogPath -Value "$stamp FAILURE code=$Code operation=$($Script:CurrentOperation) stage=$Stage" -Encoding UTF8
        Add-Content -Path $LogPath -Value (($ErrorRecord | Format-List * -Force | Out-String).TrimEnd()) -Encoding UTF8
    } catch {
        Write-Host "[team-skills] Не удалось записать полное исключение в update-log: $($_.Exception.Message)"
    }
}

function Get-ValidatedEnvInt($Name, $DefaultValue, $Minimum, $Maximum) {
    $raw = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $DefaultValue
    }
    $parsed = 0
    if (-not [int]::TryParse($raw, [ref]$parsed) -or $parsed -lt $Minimum -or $parsed -gt $Maximum) {
        throw (New-TeamSkillsException "UNKNOWN_FAILURE" "configuration" "$Name должен быть целым числом в диапазоне $Minimum..$Maximum.")
    }
    return $parsed
}

function Initialize-DownloadSettings() {
    $Script:DownloadTimeoutSec = Get-ValidatedEnvInt "CODEX_TEAM_SKILLS_DOWNLOAD_TIMEOUT_SEC" 45 1 300
    $rawAttempts = [Environment]::GetEnvironmentVariable("CODEX_TEAM_SKILLS_DOWNLOAD_MAX_ATTEMPTS")
    if ([string]::IsNullOrWhiteSpace($rawAttempts)) {
        $Script:DownloadMaxAttemptsOverride = $null
    } else {
        $Script:DownloadMaxAttemptsOverride = Get-ValidatedEnvInt "CODEX_TEAM_SKILLS_DOWNLOAD_MAX_ATTEMPTS" 3 1 5
    }
}

function Test-TransientDownloadFailure([System.Management.Automation.ErrorRecord]$ErrorRecord) {
    $current = $ErrorRecord.Exception
    while ($current) {
        if ($current -is [System.Net.WebException]) {
            $statusName = $current.Status.ToString()
            if (@("Timeout", "ConnectFailure", "ConnectionClosed", "KeepAliveFailure", "ReceiveFailure", "SendFailure") -contains $statusName) {
                return $true
            }
            try {
                if ($current.Response -and $current.Response.StatusCode) {
                    $statusCode = [int]$current.Response.StatusCode
                    if ($statusCode -eq 408 -or $statusCode -eq 429 -or ($statusCode -ge 500 -and $statusCode -le 599)) {
                        return $true
                    }
                }
            } catch {
                # У некоторых WebException response не даёт прочитать StatusCode.
            }
        }
        $current = $current.InnerException
    }
    return $false
}

function Invoke-Download($Url, $Destination, $DefaultMaxAttempts, $Stage) {
    $maxAttempts = if ($null -ne $Script:DownloadMaxAttemptsOverride) {
        $Script:DownloadMaxAttemptsOverride
    } else {
        $DefaultMaxAttempts
    }

    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        try {
            if (Test-Path $Destination) {
                Remove-Item $Destination -Force
            }
            Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Destination -TimeoutSec $Script:DownloadTimeoutSec
            return
        } catch {
            $transient = Test-TransientDownloadFailure $_
            if (-not $transient -or $attempt -ge $maxAttempts) {
                throw (New-TeamSkillsException "DOWNLOAD_FAILED" $Stage "Не удалось скачать обязательный файл: $Url" $_.Exception)
            }
            $delay = if ($attempt -eq 1) { 2 } else { 5 }
            Write-Log "Скачивание не удалось на попытке $attempt/$maxAttempts; повтор через $delay сек. Stage=$Stage"
            Start-Sleep -Seconds $delay
        }
    }
}

function Get-Sha256($Path) {
    return (Get-FileHash -Algorithm SHA256 $Path).Hash.ToLowerInvariant()
}

function Verify-Sha256($Path, $Expected, $Stage = "checksum_verification") {
    $actual = Get-Sha256 $Path
    if ($actual -ne $Expected.ToLowerInvariant()) {
        throw (New-TeamSkillsException "CHECKSUM_MISMATCH" $Stage "Checksum mismatch для $Path.")
    }
}

function Verify-PublicKeyPin() {
    if (-not (Test-Path $PublicKeyPath)) {
        throw (New-TeamSkillsException "SIGNATURE_SETUP_FAILED" "signature_key_pin" "Public key не найден: $PublicKeyPath")
    }
    $actual = (Get-FileHash -Algorithm SHA256 $PublicKeyPath).Hash.ToLowerInvariant()
    if ($actual -ne $ExpectedPublicKeySha256) {
        throw (New-TeamSkillsException "SIGNATURE_SETUP_FAILED" "signature_key_pin" "Public key не совпадает с закреплённым якорем доверия (sha256 mismatch). Возможна подмена ключа подписи. Оставляю текущий рабочий plugin без изменений.")
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
        throw (New-TeamSkillsException "SIGNATURE_SETUP_FAILED" "signature_provider" "Не удалось инициализировать проверку подписи в Windows PowerShell 5.1. Обновление не применено; запустите свежий официальный installer." $_.Exception)
    }
}

function Test-SignatureSetup() {
    Verify-PublicKeyPin
    $rsa = New-PinnedRsaProvider
    $rsa.Dispose()
}

function Verify-Signature($PayloadPath, $SignaturePath, $Stage = "signature_verification") {
    if ($AllowUnsigned) {
        Write-Log "ВНИМАНИЕ: проверка подписи ОТКЛЮЧЕНА (CODEX_TEAM_SKILLS_ALLOW_UNSIGNED=1). Это небезопасный режим только для разработки: устанавливается НЕпроверенный код. В обычной работе не используйте."
        return
    }
    Verify-PublicKeyPin

    $rsa = New-PinnedRsaProvider

    try {
        $payload = [System.IO.File]::ReadAllBytes($PayloadPath)
        $signature = [System.IO.File]::ReadAllBytes($SignaturePath)
        $sha256Oid = [System.Security.Cryptography.CryptoConfig]::MapNameToOID("SHA256")
        $ok = $rsa.VerifyData($payload, $sha256Oid, $signature)
    } catch {
        throw (New-TeamSkillsException "SIGNATURE_INVALID" $Stage "Не удалось проверить подпись обновления в Windows PowerShell 5.1. Обновление не применено." $_.Exception)
    } finally {
        if ($rsa) { $rsa.Dispose() }
    }
    if (-not $ok) {
        throw (New-TeamSkillsException "SIGNATURE_INVALID" $Stage "Подпись обновления недействительна: $PayloadPath. Оставляю текущий рабочий plugin без изменений.")
    }
}

function Download-Signed($Url, $Destination, $Stage) {
    Invoke-Download $Url $Destination 3 "$Stage-payload"
    if ($AllowUnsigned) {
        return
    }
    $signaturePath = "$Destination.sig"
    Invoke-Download "$Url.sig" $signaturePath 3 "$Stage-signature-download"
    Verify-Signature $Destination $signaturePath "$Stage-signature"
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

function Start-PluginSwap($SourceDir) {
    $destParent = Split-Path $PluginDest -Parent
    Ensure-Directory $destParent

    $tmpDest = "$PluginDest.tmp.$PID"
    $backupDest = "$PluginDest.previous.$PID"
    if (Test-Path $tmpDest) { Remove-Item $tmpDest -Recurse -Force }
    if (Test-Path $backupDest) { Remove-Item $backupDest -Recurse -Force }

    Copy-Item $SourceDir $tmpDest -Recurse -Force

    try {
        $Script:PluginHadPrevious = Test-Path $PluginDest
        if (Test-Path $PluginDest) {
            Move-Item $PluginDest $backupDest -Force
        }
        Move-Item $tmpDest $PluginDest -Force
        $Script:PluginBackupPath = $backupDest
        $Script:PluginSwapActive = $true
    } catch {
        if (Test-Path $PluginDest) { Remove-Item $PluginDest -Recurse -Force }
        if (Test-Path $backupDest) { Move-Item $backupDest $PluginDest -Force }
        if (Test-Path $tmpDest) { Remove-Item $tmpDest -Recurse -Force }
        throw
    }
}

function Undo-PluginSwap() {
    if (-not $Script:PluginSwapActive) {
        return
    }
    try {
        if (Test-Path $PluginDest) {
            Remove-Item $PluginDest -Recurse -Force -ErrorAction Stop
        }
        if (Test-Path $PluginDest) {
            throw "Новый plugin остался на месте после попытки удаления: $PluginDest"
        }
        if ($Script:PluginHadPrevious) {
            if (-not (Test-Path $Script:PluginBackupPath)) {
                throw "Backup прежнего plugin не найден: $($Script:PluginBackupPath)"
            }
            Move-Item $Script:PluginBackupPath $PluginDest -Force -ErrorAction Stop
            if (-not (Test-Path $PluginDest)) {
                throw "Прежний plugin не появился после восстановления backup: $PluginDest"
            }
        }
    } catch {
        throw (New-TeamSkillsException "INSTALL_FAILED" "plugin_rollback" "Не удалось подтвердить восстановление прежнего plugin; transaction state сохранён для повторной попытки." $_.Exception)
    }
    $Script:PluginSwapActive = $false
    $Script:PluginBackupPath = ""
    $Script:PluginHadPrevious = $false
}

function Complete-PluginSwap() {
    if ($Script:PluginBackupPath -and (Test-Path $Script:PluginBackupPath)) {
        Remove-Item $Script:PluginBackupPath -Recurse -Force -ErrorAction SilentlyContinue
    }
    $Script:PluginSwapActive = $false
    $Script:PluginBackupPath = ""
    $Script:PluginHadPrevious = $false
}

function Install-SupportFiles($SupportDir) {
    Ensure-Directory $BinDir
    foreach ($file in Get-ChildItem $SupportDir -File) {
        $dest = Join-Path $BinDir $file.Name
        if ($file.Name -eq "update-team-skills.ps1") {
            $dest = "$dest.next"
        }
        $stagedDest = "$dest.replace.$PID"
        try {
            Copy-Item $file.FullName $stagedDest -Force
            Move-Item $stagedDest $dest -Force
        } finally {
            if (Test-Path $stagedDest) {
                Remove-Item $stagedDest -Force -ErrorAction SilentlyContinue
            }
        }
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
    Write-JsonAtomically $StatePath $state
}

function Write-RepairState($Manifest) {
    $repair = [ordered]@{
        schema_version = 1
        completed_at = (Get-Date).ToUniversalTime().ToString("o")
        release_id = $Manifest.release_id
        support_files_refreshed = $true
        registry_repaired = $true
        cache_invalidated = $true
        scheduled_task_present = $true
        plugin_changed = $false
        updater_version = $UpdaterVersion
    }
    Write-JsonAtomically $RepairStatePath $repair
}

function Get-ReleaseManifest($WorkDir) {
    $latestPath = Join-Path $WorkDir "latest.json"
    $manifestPath = Join-Path $WorkDir "manifest.json"
    $effectiveManifestUrl = $ManifestUrl

    if (-not $effectiveManifestUrl) {
        $Script:CurrentStage = "latest_metadata"
        Write-Log "Скачиваю signed latest.json."
        Download-Signed $LatestUrl $latestPath "latest"
        try {
            $latest = Get-Content $latestPath -Raw | ConvertFrom-Json
            $effectiveManifestUrl = $latest.manifest_url
        } catch {
            throw (New-TeamSkillsException "INSTALL_FAILED" "latest_metadata_parse" "Не удалось прочитать latest.json." $_.Exception)
        }
        if ([string]::IsNullOrWhiteSpace($effectiveManifestUrl)) {
            throw (New-TeamSkillsException "INSTALL_FAILED" "latest_metadata_parse" "latest.json не содержит manifest_url.")
        }
    }

    $Script:CurrentStage = "manifest_metadata"
    Write-Log "Скачиваю signed manifest.json."
    Download-Signed $effectiveManifestUrl $manifestPath "manifest"
    try {
        return (Get-Content $manifestPath -Raw | ConvertFrom-Json)
    } catch {
        throw (New-TeamSkillsException "INSTALL_FAILED" "manifest_metadata_parse" "Не удалось прочитать manifest.json." $_.Exception)
    }
}

function Download-SupportFiles($Manifest, $SupportDir) {
    Ensure-Directory $SupportDir
    foreach ($entry in @($Manifest.support_files)) {
        if ([string]::IsNullOrWhiteSpace($entry.name) -or [string]::IsNullOrWhiteSpace($entry.url) -or [string]::IsNullOrWhiteSpace($entry.sha256)) {
            throw (New-TeamSkillsException "INSTALL_FAILED" "support_manifest" "manifest содержит неполное описание support file.")
        }
        $dest = Join-Path $SupportDir $entry.name
        $stageName = "support-$($entry.name)"
        $Script:CurrentStage = $stageName
        Invoke-Download $entry.url $dest 2 "$stageName-download"
        Verify-Sha256 $dest $entry.sha256 "$stageName-checksum"
    }
}

function Invoke-RegistryRepair() {
    try {
        Update-Marketplace $PluginDest
        Update-CodexRegistry
    } catch {
        throw (New-TeamSkillsException "INSTALL_FAILED" "registry_repair" "Не удалось восстановить marketplace/config." $_.Exception)
    }
}

function Invoke-CacheInvalidation() {
    try {
        Invalidate-CodexPluginCache
    } catch {
        throw (New-TeamSkillsException "INSTALL_FAILED" "cache_invalidation" "Не удалось инвалидировать Codex plugin cache." $_.Exception)
    }
}

function Invoke-ScheduleRegistration() {
    $bootstrapScript = Join-Path $BinDir "bootstrap-team-skills.ps1"
    if (-not (Test-Path $bootstrapScript)) {
        throw (New-TeamSkillsException "SCHEDULE_FAILED" "schedule_registration" "Bootstrap не найден после обновления support files.")
    }

    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $bootstrapScript -RegisterAutoUpdate 2>&1 |
            ForEach-Object { Write-Host $_ }
        $bootstrapExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($bootstrapExitCode -ne 0) {
        throw (New-TeamSkillsException "SCHEDULE_FAILED" "schedule_registration" "Bootstrap не смог зарегистрировать Scheduled Task; exit code $bootstrapExitCode.")
    }

    try {
        $task = Get-ScheduledTask -TaskName "Codex Team Skills Auto Update" -ErrorAction Stop
        if (-not $task) {
            throw "Scheduled Task отсутствует после регистрации."
        }
    } catch {
        throw (New-TeamSkillsException "SCHEDULE_FAILED" "schedule_verification" "Не удалось подтвердить Scheduled Task после регистрации." $_.Exception)
    }
}

function Repair-Install($WorkDir) {
    if (-not (Test-Path (Join-Path $PluginDest ".codex-plugin\plugin.json"))) {
        throw (New-TeamSkillsException "PLUGIN_MISSING" "plugin_precondition" "Repair не применён: plugin не найден: $PluginDest. Запустите полный официальный installer.")
    }

    $Script:CurrentStage = "signature_setup"
    Test-SignatureSetup

    if ($AllowUnsigned) {
        Write-Log "ВНИМАНИЕ: repair использует CODEX_TEAM_SKILLS_ALLOW_UNSIGNED=1. Режим разрешён только для локальной разработки."
    }

    $manifest = Get-ReleaseManifest $WorkDir
    $supportDir = Join-Path $WorkDir "support"
    Download-SupportFiles $manifest $supportDir

    $Script:CurrentStage = "support_install"
    try {
        Install-SupportFiles $supportDir
    } catch {
        throw (New-TeamSkillsException "INSTALL_FAILED" "support_install" "Не удалось атомарно обновить support files." $_.Exception)
    }

    $Script:CurrentStage = "registry_repair"
    Invoke-RegistryRepair
    $Script:CurrentStage = "cache_invalidation"
    Invoke-CacheInvalidation

    $Script:CurrentStage = "schedule_registration"
    Invoke-ScheduleRegistration

    $Script:CurrentStage = "repair_state"
    try {
        Clear-FailureState
        Write-RepairState $manifest
    } catch {
        throw (New-TeamSkillsException "INSTALL_FAILED" "repair_state" "Не удалось записать last-repair state." $_.Exception)
    }
    Write-LogSafe "Repair завершён: support files, registry/cache и Scheduled Task восстановлены; plugin и last_success_at не менялись. Перезапустите Codex."
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

$scriptFailed = $false
$workDir = $null

try {
    Ensure-Directory $CacheDir
    Ensure-Directory $StateDir
    Ensure-Directory $LogDir
    Ensure-Directory $BinDir

    $Script:CurrentStage = "configuration"
    Initialize-DownloadSettings

    $workDir = Join-Path $CacheDir ("work-" + [guid]::NewGuid().ToString("N"))
    Ensure-Directory $workDir

    if ($RepairInstall) {
        Repair-Install $workDir
    } else {
        $manifest = Get-ReleaseManifest $workDir
        $bundleUrl = $manifest.plugin_bundle.url
        if ([string]::IsNullOrWhiteSpace($bundleUrl) -or [string]::IsNullOrWhiteSpace($manifest.plugin_bundle.sha256)) {
            throw (New-TeamSkillsException "INSTALL_FAILED" "bundle_manifest" "manifest не содержит полный plugin_bundle.")
        }

        $bundlePath = Join-Path $workDir "team-skills-bundle.zip"
        $expandedDir = Join-Path $workDir "expanded"
        $supportDir = Join-Path $workDir "support"

        $Script:CurrentStage = "bundle_download"
        Write-Log "Скачиваю plugin bundle."
        Invoke-Download $bundleUrl $bundlePath 3 "bundle_download"
        Verify-Sha256 $bundlePath $manifest.plugin_bundle.sha256 "bundle_checksum"
        Download-SupportFiles $manifest $supportDir

        $Script:CurrentStage = "bundle_validation"
        try {
            Expand-Archive -Path $bundlePath -DestinationPath $expandedDir -Force
            $pluginRoot = Find-PluginRoot $expandedDir
            $pluginManifest = Get-Content (Join-Path $pluginRoot ".codex-plugin\plugin.json") -Raw | ConvertFrom-Json
            if ($pluginManifest.version -ne $manifest.runtime_version) {
                throw "runtime_version mismatch: plugin=$($pluginManifest.version) manifest=$($manifest.runtime_version)"
            }
        } catch {
            throw (New-TeamSkillsException "INSTALL_FAILED" "bundle_validation" "Plugin bundle не прошёл структурную проверку." $_.Exception)
        }

        $Script:CurrentStage = "support_install"
        try {
            Install-SupportFiles $supportDir
        } catch {
            throw (New-TeamSkillsException "INSTALL_FAILED" "support_install" "Не удалось атомарно обновить support files." $_.Exception)
        }

        $Script:CurrentStage = "registry_repair"
        Invoke-RegistryRepair

        $Script:CurrentStage = "plugin_swap"
        try {
            Clear-FailureState
            Start-PluginSwap $pluginRoot
            $Script:CurrentStage = "cache_invalidation"
            Invoke-CacheInvalidation
            $Script:CurrentStage = "success_state"
            $signatureState = if ($AllowUnsigned) { "unsigned-development" } else { "signed" }
            Write-State $manifest $bundleUrl $signatureState
            Complete-PluginSwap
        } catch {
            $transactionError = $_
            Undo-PluginSwap
            if ($transactionError.Exception.Data.Contains("TeamSkillsCode")) {
                throw $transactionError.Exception
            }
            throw (New-TeamSkillsException "INSTALL_FAILED" $Script:CurrentStage "Не удалось атомарно заменить plugin, инвалидировать cache и записать success state." $transactionError.Exception)
        }

        Write-LogSafe "Установлена проверенная версия team-skills: product=$($manifest.product_version) runtime=$($manifest.runtime_version) release=$($manifest.release_id)."
        Write-LogSafe "Перезапустите Codex, чтобы он перечитал plugin после cache invalidation; runtime visibility cannot be proven from shell."
    }
} catch {
    $failureRecord = $_
    try {
        Undo-PluginSwap
    } catch {
        Write-LogSafe "Не удалось автоматически откатить plugin swap: $($_.Exception.Message)"
    }

    $code = Get-TeamSkillsErrorCode $failureRecord.Exception
    $stage = Get-TeamSkillsErrorStage $failureRecord.Exception
    try {
        Write-FailureState $code $stage
    } catch {
        Write-LogSafe "Не удалось записать last-failure.json: $($_.Exception.Message)"
    }
    Write-ExceptionLog $failureRecord $code $stage
    Write-Error "[$code] $(Get-SafeFailureMessage $code) Stage=$stage" -ErrorAction Continue
    $scriptFailed = $true
} finally {
    if ($workDir -and (Test-Path $workDir)) {
        Remove-Item $workDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

if ($scriptFailed) {
    exit 1
}
exit 0
