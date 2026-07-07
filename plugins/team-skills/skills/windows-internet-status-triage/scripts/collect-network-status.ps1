param(
    [string]$ProbeHost = ""
)

$ErrorActionPreference = "Continue"

$internetKey = "HKLM:\SYSTEM\CurrentControlSet\Services\NlaSvc\Parameters\Internet"
$ncsi = Get-ItemProperty -LiteralPath $internetKey -ErrorAction SilentlyContinue
if (-not $ProbeHost -and $ncsi.ActiveDnsProbeHost) {
    $ProbeHost = $ncsi.ActiveDnsProbeHost
}
if (-not $ProbeHost) {
    $ProbeHost = "dns.msftncsi.com"
}

$proxyEnvironment = @()
try {
    $proxyEnvironment = @(
        cmd /c set 2>$null |
            Where-Object { $_ -match "proxy" } |
            ForEach-Object {
                $name, $value = $_ -split "=", 2
                [pscustomobject]@{ Name = $name; Value = $value }
            }
    )
} catch {
    $proxyEnvironment = @([pscustomobject]@{ Name = "error"; Value = $_.Exception.Message })
}

function Invoke-CurlCapture {
    param(
        [string[]]$Arguments
    )
    try {
        $output = & curl.exe @Arguments 2>&1
        [pscustomobject]@{
            ExitCode = $LASTEXITCODE
            Output = ($output | ForEach-Object { $_.ToString() }) -join "`n"
        }
    } catch {
        [pscustomobject]@{
            ExitCode = $null
            Output = $_.Exception.Message
        }
    }
}

$msftProbeNormal = Invoke-CurlCapture -Arguments @("-sS", "--max-time", "15", "http://www.msftconnecttest.com/connecttest.txt")
$msftProbeNoProxy = Invoke-CurlCapture -Arguments @("-sS", "--max-time", "15", "--noproxy", "*", "http://www.msftconnecttest.com/connecttest.txt")

[ordered]@{
    Timestamp = (Get-Date).ToString("s")
    NetConnectionProfile = @(Get-NetConnectionProfile -ErrorAction SilentlyContinue | Select-Object Name, InterfaceAlias, NetworkCategory, IPv4Connectivity, IPv6Connectivity)
    NcsiRegistry = if ($ncsi) {
        [ordered]@{
            ActiveDnsProbeHost = $ncsi.ActiveDnsProbeHost
            ActiveDnsProbeContent = $ncsi.ActiveDnsProbeContent
            ActiveWebProbeHost = $ncsi.ActiveWebProbeHost
            ActiveWebProbePath = $ncsi.ActiveWebProbePath
            EnableActiveProbing = $ncsi.EnableActiveProbing
        }
    } else { $null }
    DnsProbe = @(Resolve-DnsName $ProbeHost -ErrorAction SilentlyContinue | Select-Object Name, Type, IPAddress, NameHost)
    WinHttpProxy = (netsh winhttp show proxy) -join "`n"
    ProxyEnvironment = $proxyEnvironment
    MsftConnectTestHttp = $msftProbeNormal
    MsftConnectTestHttpNoProxy = $msftProbeNoProxy
} | ConvertTo-Json -Depth 6
