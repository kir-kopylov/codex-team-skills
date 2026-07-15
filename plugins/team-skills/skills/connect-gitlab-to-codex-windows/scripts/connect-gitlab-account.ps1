#requires -Version 5.1

[CmdletBinding()]
param(
    [ValidatePattern('^[A-Za-z0-9.-]+$')]
    [string]$GitLabHost = 'gitlab.com',

    [switch]$Replace,

    [switch]$HostWide
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($env:OS -ne 'Windows_NT') {
    throw 'Этот script предназначен только для Windows.'
}

$gitCommand = Get-Command git -ErrorAction SilentlyContinue
if ($null -eq $gitCommand) {
    throw 'Git не найден. Сначала установите Git for Windows.'
}

$gitVersion = & git --version
if ($LASTEXITCODE -ne 0) {
    throw 'Не удалось получить версию Git.'
}

$gcmVersion = & git credential-manager --version 2>$null
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace(($gcmVersion -join ''))) {
    throw 'Git Credential Manager не найден. Восстановите его через Git for Windows.'
}

$helperValues = @(& git config --get-all credential.helper 2>$null)
if (-not ($helperValues | Where-Object { $_ -match '(?i)manager' })) {
    & git credential-manager configure | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'Не удалось настроить Git Credential Manager как credential helper.'
    }
    $helperValues = @(& git config --get-all credential.helper 2>$null)
}

if (-not ($helperValues | Where-Object { $_ -match '(?i)manager' })) {
    throw 'Git Credential Manager установлен, но не появился в credential.helper.'
}

if ($helperValues | Where-Object { $_ -match '(?i)(^|\s)store(?:\s|$)' }) {
    throw 'Обнаружен plaintext credential.helper=store. Уберите его перед сохранением PAT.'
}

$useHttpPathKey = "credential.https://$GitLabHost.useHttpPath"
if ($HostWide) {
    & git config --global $useHttpPathKey false
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось настроить host-wide credential для $GitLabHost."
    }
}
else {
    $effectiveUseHttpPath = & git config --get-urlmatch credential.useHttpPath "https://$GitLabHost" 2>$null
    if ((($effectiveUseHttpPath -join '').Trim()).ToLowerInvariant() -eq 'true') {
        throw 'Для этого host включён credential.useHttpPath=true. Запустите с -HostWide только если здесь используется один аккаунт.'
    }
}

$gitLabUser = (Read-Host 'Имя пользователя GitLab').Trim()
if ([string]::IsNullOrWhiteSpace($gitLabUser)) {
    throw 'Имя пользователя не может быть пустым.'
}

if ($Replace) {
    $eraseInput = "protocol=https`nhost=$GitLabHost`n`n"
    $eraseInput | & git credential-manager erase --no-ui
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось удалить старый credential для $GitLabHost."
    }
}

$secureToken = Read-Host 'Personal Access Token (ввод скрыт)' -AsSecureString
$bstr = [IntPtr]::Zero
$plainToken = $null
$storeInput = $null

try {
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
    $plainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    if ([string]::IsNullOrWhiteSpace($plainToken)) {
        throw 'Token не может быть пустым.'
    }

    $storeInput = "protocol=https`nhost=$GitLabHost`nusername=$gitLabUser`npassword=$plainToken`n`n"
    $storeInput | & git credential-manager store --no-ui
    if ($LASTEXITCODE -ne 0) {
        throw "Git Credential Manager не сохранил credential для $GitLabHost."
    }
}
finally {
    $storeInput = $null
    $plainToken = $null
    $secureToken = $null
    if ($bstr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
    $bstr = [IntPtr]::Zero
}

$lookupInput = "protocol=https`nhost=$GitLabHost`nusername=$gitLabUser`n`n"
$lookupOutput = @($lookupInput | & git credential-manager get --no-ui 2>$null)
$lookupExitCode = $LASTEXITCODE
$hasUsername = $false
$hasPassword = $false

foreach ($line in $lookupOutput) {
    if ($line.StartsWith('username=', [System.StringComparison]::Ordinal)) {
        $hasUsername = $line.Length -gt 'username='.Length
    }
    elseif ($line.StartsWith('password=', [System.StringComparison]::Ordinal)) {
        $hasPassword = $line.Length -gt 'password='.Length
    }
}

$line = $null
$lookupOutput = $null
$lookupInput = $null

if ($lookupExitCode -ne 0 -or -not $hasUsername -or -not $hasPassword) {
    throw 'Credential был отправлен в GCM, но локальная проверка чтения не подтвердила оба поля.'
}

Write-Output 'LOCAL_CREDENTIAL_READY'
Write-Output "Git: $gitVersion"
Write-Output "Git Credential Manager: $gcmVersion"
Write-Output "Host: $GitLabHost"
Write-Output 'Username сохранён: да'
Write-Output 'Token сохранён: да'
Write-Output 'Удалённый доступ к GitLab: не проверен'
