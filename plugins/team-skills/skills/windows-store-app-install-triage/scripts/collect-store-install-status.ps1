param(
    [string]$StoreId = "",
    [string]$ExpectedPackagePart = ""
)

$ErrorActionPreference = "Continue"

function Invoke-Capture {
    param([scriptblock]$Script)
    try {
        $output = & $Script 2>&1 | Out-String
        if ([string]::IsNullOrWhiteSpace($output)) {
            return ""
        }
        return $output.Trim()
    }
    catch {
        return "ERROR: $($_.Exception.Message)"
    }
}

function Redact-Text {
    param([AllowNull()][string]$Value)
    if ($null -eq $Value) {
        return $null
    }
    $redacted = $Value -replace "(https?://)([^/@:\s]+):([^/@\s]+)@", "`$1<redacted>@"
    $redacted = $redacted -replace "(?i)(token|password|passwd|secret|apikey|api_key|sig)=([^;&\s]+)", "`$1=<redacted>"
    return $redacted
}

function Select-DsregLine {
    param(
        [string[]]$Lines,
        [string]$Name
    )
    $line = $Lines | Where-Object { $_ -match "^\s*$([regex]::Escape($Name))\s*:" } | Select-Object -First 1
    if ($line) {
        return $line.Trim()
    }
    return $null
}

function Select-AppxPackage {
    param([string]$Name)
    Get-AppxPackage -Name $Name -ErrorAction SilentlyContinue |
        Select-Object Name, PackageFullName, PackageFamilyName, Version, Status, InstallLocation
}

$profiles = Get-NetConnectionProfile -ErrorAction SilentlyContinue |
    Select-Object Name, InterfaceAlias, NetworkCategory, IPv4Connectivity, IPv6Connectivity

$hasInternetProfile = @($profiles | Where-Object { "$($_.IPv4Connectivity)" -eq "Internet" }).Count -gt 0

$dsreg = Invoke-Capture { dsregcmd /status }
$dsregLines = $dsreg -split "`r?`n"
$dsregSelected = [ordered]@{
    AzureAdJoined = Select-DsregLine -Lines $dsregLines -Name "AzureAdJoined"
    WorkplaceJoined = Select-DsregLine -Lines $dsregLines -Name "WorkplaceJoined"
    WamDefaultSet = Select-DsregLine -Lines $dsregLines -Name "WamDefaultSet"
    DeviceAuthStatus = Select-DsregLine -Lines $dsregLines -Name "DeviceAuthStatus"
}

$packageNames = @(
    "Microsoft.DesktopAppInstaller",
    "Microsoft.WindowsStore",
    "Microsoft.StorePurchaseApp"
)

$appxPackages = foreach ($name in $packageNames) {
    Select-AppxPackage -Name $name
}

$services = foreach ($name in @("ClipSVC", "InstallService", "TokenBroker", "wlidsvc", "AppXSvc", "LicenseManager", "BITS", "DoSvc", "wuauserv")) {
    Get-Service -Name $name -ErrorAction SilentlyContinue |
        Select-Object Name, Status, StartType, DisplayName
}

$internetSettingsRaw = Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings" -ErrorAction SilentlyContinue
$internetSettings = $null
if ($internetSettingsRaw) {
    $internetSettings = [ordered]@{
        ProxyEnable = $internetSettingsRaw.ProxyEnable
        ProxyServer = Redact-Text $internetSettingsRaw.ProxyServer
        AutoConfigURL = Redact-Text $internetSettingsRaw.AutoConfigURL
    }
}

$proxyEnv = @()
$envOutput = Invoke-Capture { cmd.exe /c set }
foreach ($line in ($envOutput -split "`r?`n")) {
    if ($line -match "^([^=]+)=(.*)$") {
        $name = $Matches[1]
        $value = $Matches[2]
        if ($name -match "proxy") {
            $proxyEnv += [ordered]@{
                Name = $name
                Value = Redact-Text $value
            }
        }
    }
}

if (-not $proxyEnv) {
    $proxyEnv = @()
}

function Get-ProxyEnvironment {
    param([object[]]$Values)
    foreach ($entry in $Values) {
        [ordered]@{
            Name = $entry.Name
            Value = $entry.Value
        }
    }
}

$wingetShow = ""
if (-not [string]::IsNullOrWhiteSpace($StoreId)) {
    $wingetShow = Invoke-Capture { winget show --id $StoreId --source msstore }
}

$installedCandidate = ""
if (-not [string]::IsNullOrWhiteSpace($ExpectedPackagePart)) {
    $pattern = "*$ExpectedPackagePart*"
    $installedCandidate = Get-AppxPackage -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like $pattern -or $_.PackageFamilyName -like $pattern } |
        Select-Object Name, PackageFullName, PackageFamilyName, Version, Status
}

$result = [ordered]@{
    collectedAt = (Get-Date).ToString("o")
    input = [ordered]@{
        storeId = $StoreId
        expectedPackagePart = $ExpectedPackagePart
    }
    internetGate = [ordered]@{
        hasIPv4InternetProfile = $hasInternetProfile
        requiredBeforeStoreTriage = "IPv4Connectivity must be Internet"
    }
    netConnectionProfile = $profiles
    winget = [ordered]@{
        info = Invoke-Capture { winget --info }
        sources = Invoke-Capture { winget source list }
        msstoreShow = $wingetShow
    }
    dsreg = [ordered]@{
        selectedLines = $dsregSelected
    }
    appxPackages = $appxPackages
    installedCandidate = $installedCandidate
    services = $services
    proxy = [ordered]@{
        winhttp = Redact-Text (Invoke-Capture { netsh winhttp show proxy })
        userInternetSettings = $internetSettings
        environment = @(Get-ProxyEnvironment -Values $proxyEnv)
    }
    loopbackExemptions = Invoke-Capture { CheckNetIsolation.exe LoopbackExempt -s }
}

$result | ConvertTo-Json -Depth 8
