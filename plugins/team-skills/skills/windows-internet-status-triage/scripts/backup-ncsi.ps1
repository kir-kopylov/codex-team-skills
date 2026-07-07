param(
    [string]$OutDir = $env:USERPROFILE
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $OutDir)) {
    New-Item -ItemType Directory -Path $OutDir | Out-Null
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = Join-Path $OutDir "ncsi-internet-backup-$stamp.reg"
reg export "HKLM\SYSTEM\CurrentControlSet\Services\NlaSvc\Parameters\Internet" $backup /y | Out-Null

[pscustomobject]@{
    BackupRegPath = $backup
    Timestamp = $stamp
}
