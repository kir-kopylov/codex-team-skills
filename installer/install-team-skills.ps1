param(
    [switch]$SkipSchedule,
    [switch]$ValidateOnly,
    [string]$ManifestUrl = $env:CODEX_TEAM_SKILLS_MANIFEST_URL
)

$ErrorActionPreference = "Stop"

$RepoReleaseBase = "https://github.com/kir-kopylov/codex-team-skills/releases/latest/download"
$InstallRoot = if ($env:CODEX_TEAM_SKILLS_HOME) { $env:CODEX_TEAM_SKILLS_HOME } else { Join-Path $env:LOCALAPPDATA "CodexTeamSkills" }
$BinDir = Join-Path $InstallRoot "bin"
$LogDir = Join-Path $InstallRoot "logs"
$BootstrapScript = Join-Path $BinDir "bootstrap-team-skills.ps1"

if (-not $ManifestUrl) {
    $ManifestUrl = "$RepoReleaseBase/manifest.json"
}

if ($ValidateOnly) {
    Write-Host "[team-skills] ValidateOnly: install-team-skills.ps1 parsed and initialized."
    exit 0
}

function Write-Info($Message) {
    Write-Host "[team-skills] $Message"
}

function Ensure-Directory($Path) {
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Install-SupportFile($Name) {
    $source = Join-Path $PSScriptRoot $Name
    $dest = Join-Path $BinDir $Name
    if (Test-Path $source) {
        Copy-Item $source $dest -Force
        return
    }

    $url = "$RepoReleaseBase/$Name"
    Write-Info "Скачиваю служебный файл $Name"
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $dest
}

function Invoke-BootstrapProcess([switch]$RegisterAutoUpdate) {
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        if ($RegisterAutoUpdate) {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $BootstrapScript -RegisterAutoUpdate 2>&1 |
                ForEach-Object { Write-Host $_ }
        } else {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $BootstrapScript 2>&1 |
                ForEach-Object { Write-Host $_ }
        }
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

Ensure-Directory $InstallRoot
Ensure-Directory $BinDir
Ensure-Directory $LogDir

Install-SupportFile "bootstrap-team-skills.ps1"
Install-SupportFile "update-team-skills.ps1"
Install-SupportFile "uninstall-team-skills.ps1"
Install-SupportFile "team-skills-status.ps1"
Install-SupportFile "team-skills-public-key.pem"

Write-Info "Ставлю последнюю проверенную версию командных Codex skills."
$previousManifestUrl = $env:CODEX_TEAM_SKILLS_MANIFEST_URL
try {
    if ($ManifestUrl) {
        $env:CODEX_TEAM_SKILLS_MANIFEST_URL = $ManifestUrl
    }
    $updateExitCode = Invoke-BootstrapProcess
} finally {
    if ($null -eq $previousManifestUrl) {
        Remove-Item Env:\CODEX_TEAM_SKILLS_MANIFEST_URL -ErrorAction SilentlyContinue
    } else {
        $env:CODEX_TEAM_SKILLS_MANIFEST_URL = $previousManifestUrl
    }
}
if ($updateExitCode -ne 0) {
    throw "Проверенное обновление завершилось с exit code $updateExitCode. Scheduled Task не создаётся."
}

if ($SkipSchedule) {
    Write-Info "Автообновление пропущено по параметру SkipSchedule."
} else {
    $scheduleExitCode = Invoke-BootstrapProcess -RegisterAutoUpdate
    if ($scheduleExitCode -ne 0) {
        throw "Plugin обновлён, но Scheduled Task не создан; bootstrap exit code $scheduleExitCode."
    }
}

Write-Info "Готово. Перезапустите Codex, чтобы он перечитал plugin team-skills."
Write-Info "Проверка статуса: powershell -NoProfile -ExecutionPolicy Bypass -File `"$BinDir\team-skills-status.ps1`""
