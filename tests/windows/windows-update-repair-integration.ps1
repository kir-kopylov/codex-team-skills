$ErrorActionPreference = "Stop"

$TaskName = "Codex Team Skills Auto Update"
$RepoRoot = $env:GITHUB_WORKSPACE
$DistDir = Join-Path $RepoRoot "dist"
$Updater = Join-Path $DistDir "update-team-skills.ps1"
$TestRoot = Join-Path $env:RUNNER_TEMP ("team-skills-repair-" + [guid]::NewGuid().ToString("N"))
$InstallRoot = Join-Path $TestRoot "install"
$BinDir = Join-Path $InstallRoot "bin"
$StateDir = Join-Path $InstallRoot "state"
$PluginDir = Join-Path $TestRoot "plugin"
$MarketplaceRoot = Join-Path $TestRoot "home"
$MarketplacePath = Join-Path $MarketplaceRoot ".agents\plugins\marketplace.json"
$ConfigPath = Join-Path $MarketplaceRoot ".codex\config.toml"
$CachePath = Join-Path $MarketplaceRoot ".codex\plugins\cache\codex-team-skills"
$ServerRoot = Join-Path $TestRoot "server"
$ServerProcess = $null
$TaskCleanupAllowed = $false

$ManagedEnvNames = @(
    "CODEX_TEAM_SKILLS_HOME",
    "CODEX_TEAM_SKILLS_PLUGIN_DIR",
    "CODEX_TEAM_SKILLS_MARKETPLACE_ROOT",
    "CODEX_TEAM_SKILLS_MARKETPLACE",
    "CODEX_TEAM_SKILLS_CODEX_CONFIG",
    "CODEX_TEAM_SKILLS_CODEX_PLUGIN_CACHE_DIR",
    "CODEX_TEAM_SKILLS_PUBLIC_KEY",
    "CODEX_TEAM_SKILLS_LATEST_URL",
    "CODEX_TEAM_SKILLS_MANIFEST_URL",
    "CODEX_TEAM_SKILLS_ALLOW_UNSIGNED",
    "CODEX_TEAM_SKILLS_DOWNLOAD_TIMEOUT_SEC",
    "CODEX_TEAM_SKILLS_DOWNLOAD_MAX_ATTEMPTS"
)
$PreviousEnv = @{}
foreach ($name in $ManagedEnvNames) {
    $PreviousEnv[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

function Assert-True($Condition, $Message) {
    if (-not $Condition) {
        throw "ASSERTION FAILED: $Message"
    }
}

function Set-TestEnv($Name, $Value) {
    [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
}

function Invoke-WindowsPowerShell($ScriptPath, [string[]]$Arguments = @()) {
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ScriptPath @Arguments 2>&1
        $exitCode = $LASTEXITCODE
        return [pscustomobject]@{
            ExitCode = $exitCode
            Output = @($output)
            Text = ($output | Out-String)
        }
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

function Get-FreeTcpPort() {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try {
        return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
    } finally {
        $listener.Stop()
    }
}

try {
    New-Item -ItemType Directory -Path $BinDir, $StateDir, $PluginDir, $MarketplaceRoot, $CachePath, $ServerRoot -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $PluginDir ".codex-plugin") -Force | Out-Null
    Set-Content -Path (Join-Path $PluginDir ".codex-plugin\plugin.json") -Value '{"name":"team-skills","version":"0.1.0-test"}' -Encoding UTF8
    Set-Content -Path (Join-Path $PluginDir "plugin-marker.txt") -Value "plugin-must-stay" -Encoding UTF8
    Set-Content -Path (Join-Path $CachePath "cache-marker.txt") -Value "stale-cache" -Encoding UTF8
    Copy-Item $Updater (Join-Path $BinDir "update-team-skills.ps1") -Force
    Copy-Item (Join-Path $DistDir "team-skills-public-key.pem") (Join-Path $BinDir "team-skills-public-key.pem") -Force

    $statePath = Join-Path $StateDir "state.json"
    $originalState = '{"last_success_at":"2001-02-03T04:05:06Z","release_id":"existing-success","updater_version":"1.1.0"}'
    Set-Content -Path $statePath -Value $originalState -Encoding UTF8
    $stateBefore = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($statePath))
    $pluginMarkerPath = Join-Path $PluginDir "plugin-marker.txt"
    $pluginBefore = (Get-FileHash -Algorithm SHA256 $pluginMarkerPath).Hash

    Set-TestEnv "CODEX_TEAM_SKILLS_HOME" $InstallRoot
    Set-TestEnv "CODEX_TEAM_SKILLS_PLUGIN_DIR" $PluginDir
    Set-TestEnv "CODEX_TEAM_SKILLS_MARKETPLACE_ROOT" $MarketplaceRoot
    Set-TestEnv "CODEX_TEAM_SKILLS_MARKETPLACE" $MarketplacePath
    Set-TestEnv "CODEX_TEAM_SKILLS_CODEX_CONFIG" $ConfigPath
    Set-TestEnv "CODEX_TEAM_SKILLS_CODEX_PLUGIN_CACHE_DIR" $CachePath
    Set-TestEnv "CODEX_TEAM_SKILLS_PUBLIC_KEY" (Join-Path $BinDir "team-skills-public-key.pem")
    Set-TestEnv "CODEX_TEAM_SKILLS_DOWNLOAD_TIMEOUT_SEC" "1"
    Set-TestEnv "CODEX_TEAM_SKILLS_DOWNLOAD_MAX_ATTEMPTS" "1"
    Set-TestEnv "CODEX_TEAM_SKILLS_ALLOW_UNSIGNED" $null
    Set-TestEnv "CODEX_TEAM_SKILLS_MANIFEST_URL" $null

    $closedPort = Get-FreeTcpPort
    Set-TestEnv "CODEX_TEAM_SKILLS_LATEST_URL" "http://127.0.0.1:$closedPort/latest.json"
    $failedUpdate = Invoke-WindowsPowerShell $Updater
    Assert-True ($failedUpdate.ExitCode -ne 0) "unavailable localhost update must fail"

    $failurePath = Join-Path $StateDir "last-failure.json"
    Assert-True (Test-Path $failurePath) "DOWNLOAD_FAILED state must be created"
    $failure = Get-Content $failurePath -Raw | ConvertFrom-Json
    Assert-True ($failure.code -eq "DOWNLOAD_FAILED") "failure code must be DOWNLOAD_FAILED"
    Assert-True ($failure.operation -eq "update") "failure operation must be update"
    Assert-True ($failure.updater_version -eq "1.2.0") "failure must record updater 1.2.0"
    Assert-True ([Convert]::ToBase64String([System.IO.File]::ReadAllBytes($statePath)) -eq $stateBefore) "failed update must preserve state.json"
    Assert-True ((Get-FileHash -Algorithm SHA256 $pluginMarkerPath).Hash -eq $pluginBefore) "failed update must preserve plugin"

    $supportNames = @(
        "bootstrap-team-skills.ps1",
        "update-team-skills.ps1",
        "team-skills-status.ps1",
        "team-skills-public-key.pem"
    )
    foreach ($name in $supportNames) {
        Copy-Item (Join-Path $DistDir $name) (Join-Path $ServerRoot $name) -Force
    }
    Set-Content -Path (Join-Path $ServerRoot "repair-marker.txt") -Value "support-refreshed" -Encoding UTF8
    $supportNames += "repair-marker.txt"

    $serverPort = Get-FreeTcpPort
    $baseUrl = "http://127.0.0.1:$serverPort"
    $supportEntries = @()
    foreach ($name in $supportNames) {
        $path = Join-Path $ServerRoot $name
        $supportEntries += [ordered]@{
            name = $name
            url = "$baseUrl/$name"
            sha256 = (Get-FileHash -Algorithm SHA256 $path).Hash.ToLowerInvariant()
            size = (Get-Item $path).Length
        }
    }

    $manifest = [ordered]@{
        name = "team-skills"
        channel = "development"
        release_id = "repair-fixture-1"
        product_version = "repair-fixture"
        runtime_version = "0.1.0-test"
        commit = "synthetic"
        plugin_bundle = [ordered]@{
            url = "$baseUrl/not-used.zip"
            sha256 = ("0" * 64)
        }
        support_files = $supportEntries
    }
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -Path (Join-Path $ServerRoot "manifest.json") -Encoding UTF8
    $latest = [ordered]@{
        name = "team-skills"
        channel = "development"
        release_id = "repair-fixture-1"
        manifest_url = "$baseUrl/manifest.json"
    }
    $latest | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $ServerRoot "latest.json") -Encoding UTF8

    $python = (Get-Command python -ErrorAction Stop).Source
    $ServerProcess = Start-Process -FilePath $python -ArgumentList @("-m", "http.server", "$serverPort", "--bind", "127.0.0.1", "--directory", $ServerRoot) -PassThru -WindowStyle Hidden
    $serverReady = $false
    for ($probe = 0; $probe -lt 50; $probe++) {
        try {
            Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/latest.json" -TimeoutSec 1 | Out-Null
            $serverReady = $true
            break
        } catch {
            Start-Sleep -Milliseconds 100
        }
    }
    Assert-True $serverReady "local HTTP fixture server must become ready"

    $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Assert-True (-not $existingTask) "integration starts with missing Scheduled Task"
    $TaskCleanupAllowed = $true

    Set-TestEnv "CODEX_TEAM_SKILLS_LATEST_URL" "$baseUrl/latest.json"
    Set-TestEnv "CODEX_TEAM_SKILLS_ALLOW_UNSIGNED" "1"
    $repair = Invoke-WindowsPowerShell $Updater @("-RepairInstall")
    Assert-True ($repair.ExitCode -eq 0) "repair must succeed: $($repair.Text)"

    Assert-True ((Get-FileHash -Algorithm SHA256 $pluginMarkerPath).Hash -eq $pluginBefore) "repair must not change plugin"
    Assert-True ([Convert]::ToBase64String([System.IO.File]::ReadAllBytes($statePath)) -eq $stateBefore) "repair must preserve last_success_at and state.json"
    Assert-True (-not (Test-Path $failurePath)) "successful repair must clear active failure"

    $repairStatePath = Join-Path $StateDir "last-repair.json"
    Assert-True (Test-Path $repairStatePath) "successful repair must write last-repair.json"
    $repairState = Get-Content $repairStatePath -Raw | ConvertFrom-Json
    Assert-True ($repairState.release_id -eq "repair-fixture-1") "repair state release_id"
    Assert-True ($repairState.support_files_refreshed -eq $true) "support files refreshed"
    Assert-True ($repairState.registry_repaired -eq $true) "registry repaired"
    Assert-True ($repairState.cache_invalidated -eq $true) "cache invalidated"
    Assert-True ($repairState.scheduled_task_present -eq $true) "task present in repair state"
    Assert-True ($repairState.plugin_changed -eq $false) "repair state must record plugin_changed=false"

    Assert-True (Test-Path (Join-Path $BinDir "repair-marker.txt")) "support marker must be installed"
    Assert-True (Test-Path (Join-Path $BinDir "update-team-skills.ps1.next")) "updater must remain staged as .next"
    Assert-True (-not (Test-Path $CachePath)) "active cache directory must move away"
    Assert-True (@(Get-ChildItem "$CachePath.stale.*" -Directory -ErrorAction SilentlyContinue).Count -ge 1) "stale cache directory must exist"
    $marketplace = Get-Content $MarketplacePath -Raw | ConvertFrom-Json
    $teamSkillsEntries = @($marketplace.plugins | Where-Object { $_.name -eq "team-skills" })
    Assert-True ($teamSkillsEntries.Count -eq 1) "marketplace must contain exactly one team-skills entry"
    Assert-True ((Get-Content $ConfigPath -Raw).Contains("# BEGIN codex-team-skills managed block")) "Codex config must contain managed block"

    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    Assert-True ($task.Actions[0].Execute -like "*powershell.exe") "task action must use powershell.exe"
    Assert-True ($task.Actions[0].Arguments.Contains("bootstrap-team-skills.ps1")) "task action must call bootstrap"
    Assert-True ($task.Triggers[0].DaysInterval -eq 2) "task trigger must run every two days"

    $statusScript = Join-Path $BinDir "team-skills-status.ps1"
    $healthyStatus = Invoke-WindowsPowerShell $statusScript
    Assert-True ($healthyStatus.ExitCode -eq 0) "healthy status must exit zero"
    foreach ($marker in @("Автообновление: включено", "State:", "LastRunTime:", "LastTaskResult:", "NextRunTime:", "Последний успешный repair:", "Активной ошибки update/repair нет.")) {
        Assert-True ($healthyStatus.Text.Contains($marker)) "healthy status marker: $marker"
    }

    $syntheticFailure = [ordered]@{
        schema_version = 1
        failed_at = "2001-02-03T04:05:07Z"
        operation = "repair"
        stage = "synthetic"
        code = "TEST_FAILURE"
        message = "synthetic safe message"
        updater_version = "1.2.0"
    }
    $syntheticFailure | ConvertTo-Json | Set-Content -Path $failurePath -Encoding UTF8
    $failedStatus = Invoke-WindowsPowerShell $statusScript
    Assert-True ($failedStatus.Text.Contains("Активная ошибка update/repair:")) "status must show active failure heading"
    Assert-True ($failedStatus.Text.Contains("TEST_FAILURE")) "status must show active failure code"

    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
    $missingStatus = Invoke-WindowsPowerShell $statusScript
    Assert-True ($missingStatus.Text.Contains("Автообновление: отсутствует")) "status must distinguish missing task"

    Write-Host "Windows update/repair integration passed."
} finally {
    if ($TaskCleanupAllowed) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    }
    if ($ServerProcess -and -not $ServerProcess.HasExited) {
        Stop-Process -Id $ServerProcess.Id -Force -ErrorAction SilentlyContinue
    }
    foreach ($name in $ManagedEnvNames) {
        [Environment]::SetEnvironmentVariable($name, $PreviousEnv[$name], "Process")
    }
    if (Test-Path $TestRoot) {
        Remove-Item $TestRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
