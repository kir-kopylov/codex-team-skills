param(
    [Parameter(Mandatory = $true)]
    [string]$BackupRegPath,
    [switch]$SkipServiceRestart
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $BackupRegPath)) {
    throw "Backup file not found: $BackupRegPath"
}

reg import $BackupRegPath | Out-Null
ipconfig /flushdns | Out-Null

if (-not $SkipServiceRestart) {
    Restart-Service -Name Dnscache -Force -ErrorAction SilentlyContinue
    Restart-Service -Name NlaSvc -Force -ErrorAction SilentlyContinue
    Restart-Service -Name netprofm -Force -ErrorAction SilentlyContinue
    Start-Service -Name NcaSvc -ErrorAction SilentlyContinue
}

[pscustomobject]@{
    RestoredFrom = $BackupRegPath
}
