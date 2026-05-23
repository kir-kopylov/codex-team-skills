param(
    [string[]]$ForwardArgs,
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
$BootstrapVersion = "1.0.0"
$InstallRoot = if ($env:CODEX_TEAM_SKILLS_HOME) { $env:CODEX_TEAM_SKILLS_HOME } else { Join-Path $env:LOCALAPPDATA "CodexTeamSkills" }
$BinDir = Join-Path $InstallRoot "bin"
$UpdateScript = Join-Path $BinDir "update-team-skills.ps1"
$NextUpdateScript = "$UpdateScript.next"

if ($ValidateOnly) {
    Write-Host "[team-skills] ValidateOnly: bootstrap-team-skills.ps1 parsed and initialized."
    exit 0
}

if (-not (Test-Path $UpdateScript)) {
    Write-Host "[team-skills] Updater не найден: $UpdateScript"
    Write-Host "[team-skills] Запустите installer заново, чтобы восстановить support files."
    exit 1
}

if (Test-Path $NextUpdateScript) {
    Move-Item $NextUpdateScript $UpdateScript -Force
    Write-Host "[team-skills] Updater обновлён из staged .next версии."
}

$env:CODEX_TEAM_SKILLS_BOOTSTRAP_VERSION = $BootstrapVersion
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $UpdateScript @ForwardArgs
exit $LASTEXITCODE
