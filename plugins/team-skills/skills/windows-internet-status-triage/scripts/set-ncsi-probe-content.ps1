param(
    [Parameter(Mandatory = $true)]
    [string]$ExpectedContent,
    [switch]$SkipServiceRestart
)

$ErrorActionPreference = "Stop"

if ($ExpectedContent -notmatch "^[A-Za-z0-9.:_-]+$") {
    throw "ExpectedContent contains unexpected characters. Pass only the DNS probe answer, for example 131.107.255.255 or 198.18.1.205."
}

$path = "HKLM:\SYSTEM\CurrentControlSet\Services\NlaSvc\Parameters\Internet"
$before = Get-ItemProperty -LiteralPath $path
Set-ItemProperty -LiteralPath $path -Name ActiveDnsProbeContent -Value $ExpectedContent -Type String
ipconfig /flushdns | Out-Null

if (-not $SkipServiceRestart) {
    Restart-Service -Name Dnscache -Force -ErrorAction SilentlyContinue
    Restart-Service -Name NlaSvc -Force -ErrorAction SilentlyContinue
    Restart-Service -Name netprofm -Force -ErrorAction SilentlyContinue
    Start-Service -Name NcaSvc -ErrorAction SilentlyContinue
}

[pscustomobject]@{
    PreviousActiveDnsProbeContent = $before.ActiveDnsProbeContent
    NewActiveDnsProbeContent = $ExpectedContent
}
