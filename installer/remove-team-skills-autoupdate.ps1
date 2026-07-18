param(
    [switch]$DryRun,
    [switch]$Apply,
    [Parameter(ValueFromRemainingArguments = $true)]
    [object[]]$UnexpectedArguments
)

$ErrorActionPreference = "Stop"

$TaskName = "Codex Team Skills Auto Update"
$TaskPath = "\"
$AllowedActionScripts = @(
    "bootstrap-team-skills.ps1",
    "update-team-skills.ps1",
    "team-skills-auto-update-with-git-fallback.ps1"
)
$AllowedProcessScripts = @(
    "bootstrap-team-skills.ps1",
    "update-team-skills.ps1",
    "team-skills-auto-update-with-git-fallback.ps1"
)
$AllowedBinEntries = @(
    "install-team-skills.cmd",
    "install-team-skills.ps1",
    "install-team-skills.command",
    "bootstrap-team-skills.ps1",
    "bootstrap-team-skills.sh",
    "update-team-skills.ps1",
    "update-team-skills.sh",
    "update-team-skills.ps1.next",
    "team-skills-auto-update-with-git-fallback.ps1",
    "team-skills-status.ps1",
    "team-skills-status.command",
    "uninstall-team-skills.ps1",
    "uninstall-team-skills.command",
    "refresh-team-skills.command",
    "pull-skills.sh",
    "team-skills-registry.py",
    "team-skills-public-key.pem"
)
$AllowedBinDirectory = "__pycache__"
$AllowedRegistryBytecodePattern = '^team-skills-registry\.cpython-\d+\.pyc$'
$AllowedRootEntries = @("bin", "cache", "state", "logs")
$MarkerScripts = @(
    "bootstrap-team-skills.ps1",
    "update-team-skills.ps1",
    "update-team-skills.ps1.next",
    "team-skills-auto-update-with-git-fallback.ps1"
)

$UserHome = if ($HOME) { $HOME } else { $env:USERPROFILE }
$DefaultPluginPath = Join-Path $UserHome "plugins\team-skills"
$DefaultMarketplacePath = Join-Path $UserHome ".agents\plugins\marketplace.json"
$DefaultConfigPath = Join-Path $UserHome ".codex\config.toml"
$DefaultCachePath = Join-Path $UserHome ".codex\plugins\cache\codex-team-skills"

# Override не заменяет стандартный защищённый объект. Cleanup обязан доказать,
# что не изменил ни default-path, ни отдельно настроенный active-path.
$PluginPaths = @($DefaultPluginPath)
if ($env:CODEX_TEAM_SKILLS_PLUGIN_DIR) {
    $PluginPaths += $env:CODEX_TEAM_SKILLS_PLUGIN_DIR
}
$MarketplacePaths = @($DefaultMarketplacePath)
if ($env:CODEX_TEAM_SKILLS_MARKETPLACE) {
    $MarketplacePaths += $env:CODEX_TEAM_SKILLS_MARKETPLACE
} elseif ($env:CODEX_TEAM_SKILLS_MARKETPLACE_ROOT) {
    $MarketplacePaths += Join-Path $env:CODEX_TEAM_SKILLS_MARKETPLACE_ROOT ".agents\plugins\marketplace.json"
}
$ConfigPaths = @($DefaultConfigPath)
if ($env:CODEX_TEAM_SKILLS_CODEX_CONFIG) {
    $ConfigPaths += $env:CODEX_TEAM_SKILLS_CODEX_CONFIG
}
$CachePaths = @($DefaultCachePath)
if ($env:CODEX_TEAM_SKILLS_CODEX_PLUGIN_CACHE_DIR) {
    $CachePaths += $env:CODEX_TEAM_SKILLS_CODEX_PLUGIN_CACHE_DIR
}

function Write-Info($Message) {
    Write-Host "[team-skills] $Message"
}

function Exit-WithUsageError($Message) {
    Write-Host "[team-skills] ОШИБКА ВЫЗОВА: $Message"
    Write-Host "[team-skills] Использование: .\remove-team-skills-autoupdate.ps1 -DryRun | -Apply"
    exit 2
}

if ($UnexpectedArguments -and $UnexpectedArguments.Count -gt 0) {
    Exit-WithUsageError "Неизвестные аргументы: $($UnexpectedArguments -join ' ')"
}
if (($DryRun -and $Apply) -or (-not $DryRun -and -not $Apply)) {
    Exit-WithUsageError "Нужно указать ровно один режим: -DryRun или -Apply."
}

function Get-NormalizedPath($Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "Получен пустой путь."
    }
    return [System.IO.Path]::GetFullPath($Path).TrimEnd([char[]]"\/")
}

function Test-SamePath($Left, $Right) {
    $leftFull = Get-NormalizedPath $Left
    $rightFull = Get-NormalizedPath $Right
    return $leftFull.Equals($rightFull, [System.StringComparison]::OrdinalIgnoreCase)
}

function Test-SameOrDescendantPath($Candidate, $Parent) {
    $candidateFull = Get-NormalizedPath $Candidate
    $parentFull = Get-NormalizedPath $Parent
    if ($candidateFull.Equals($parentFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }
    $prefix = $parentFull + [System.IO.Path]::DirectorySeparatorChar
    return $candidateFull.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)
}

function Test-ReparsePoint($Item) {
    return (($Item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)
}

function Get-TextSha256($Text) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes([string]$Text)
        return ([System.BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
    } finally {
        $sha.Dispose()
    }
}

function Get-ProtectedFingerprint($Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return "ABSENT"
    }

    $rootItem = Get-Item -LiteralPath $Path -Force
    if (-not $rootItem.PSIsContainer) {
        return (Get-FileHash -LiteralPath $rootItem.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }

    $base = (Get-NormalizedPath $rootItem.FullName)
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($entry in @(Get-ChildItem -LiteralPath $base -Force -Recurse | Sort-Object FullName)) {
        $relative = $entry.FullName.Substring($base.Length).TrimStart([char[]]"\/").Replace("\", "/")
        if (Test-ReparsePoint $entry) {
            $lines.Add("R|$relative")
        } elseif ($entry.PSIsContainer) {
            $lines.Add("D|$relative")
        } else {
            $hash = (Get-FileHash -LiteralPath $entry.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            $lines.Add("F|$relative|$($entry.Length)|$hash")
        }
    }
    return Get-TextSha256 ($lines -join "`n")
}

function Get-ProtectedSetFingerprint($Paths) {
    $records = New-Object System.Collections.Generic.List[string]
    $seen = New-Object System.Collections.Generic.List[string]
    foreach ($path in @($Paths)) {
        $normalized = Get-NormalizedPath $path
        if (@($seen | Where-Object { Test-SamePath $_ $normalized }).Count -gt 0) {
            continue
        }
        $seen.Add($normalized)
        $fingerprint = Get-ProtectedFingerprint $normalized
        $records.Add("$($normalized.ToLowerInvariant())|$fingerprint")
    }
    $ordered = @($records | Sort-Object)
    if ($ordered.Count -eq 1) {
        return $ordered[0].Substring($ordered[0].LastIndexOf("|") + 1)
    }
    return Get-TextSha256 ($ordered -join "`n")
}

function Get-ProtectedFingerprints() {
    return [pscustomobject]@{
        Plugin = (Get-ProtectedSetFingerprint $PluginPaths)
        Marketplace = (Get-ProtectedSetFingerprint $MarketplacePaths)
        Config = (Get-ProtectedSetFingerprint $ConfigPaths)
        Cache = (Get-ProtectedSetFingerprint $CachePaths)
    }
}

function Test-ProtectedFingerprintsEqual($Before, $After) {
    return (
        $Before.Plugin -eq $After.Plugin -and
        $Before.Marketplace -eq $After.Marketplace -and
        $Before.Config -eq $After.Config -and
        $Before.Cache -eq $After.Cache
    )
}

function Get-TargetTasks() {
    if (-not (Get-Command Get-ScheduledTask -ErrorAction SilentlyContinue)) {
        throw "Команда Get-ScheduledTask недоступна: cleanup нужно запускать в Windows PowerShell 5.1 или новее."
    }
    # Task Scheduler сравнивает имена без учёта регистра; такой же identity-rule
    # нужен discovery, иначе задача с другим casing останется живой.
    return @(Get-ScheduledTask -ErrorAction Stop | Where-Object { $_.TaskName -ieq $TaskName })
}

function Get-TaskScriptPath($Task) {
    if ($Task.TaskPath -cne $TaskPath) {
        throw "Задача '$($Task.TaskPath)$($Task.TaskName)' находится не в разрешённом пути '$TaskPath$TaskName'."
    }
    $actions = @($Task.Actions)
    if ($actions.Count -ne 1) {
        throw "Scheduled Task должна содержать ровно одно действие; найдено: $($actions.Count)."
    }

    $action = $actions[0]
    if ([string]$action.Execute -ine "powershell.exe") {
        throw "Scheduled Task запускает не powershell.exe: '$($action.Execute)'."
    }
    if (-not [string]::IsNullOrWhiteSpace([string]$action.WorkingDirectory)) {
        throw "У Scheduled Task задан неожиданный WorkingDirectory."
    }

    $pattern = '(?i)^\s*-NoProfile\s+-ExecutionPolicy\s+Bypass\s+-File\s+(?:"([^"]+)"|''([^'']+)''|(\S+))\s*$'
    $match = [System.Text.RegularExpressions.Regex]::Match([string]$action.Arguments, $pattern)
    if (-not $match.Success) {
        throw "Аргументы Scheduled Task не совпадают с известным legacy-форматом."
    }
    $scriptPath = @($match.Groups[1].Value, $match.Groups[2].Value, $match.Groups[3].Value) |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
        Select-Object -First 1
    if (-not [System.IO.Path]::IsPathRooted($scriptPath)) {
        throw "Scheduled Task содержит не абсолютный путь к скрипту."
    }
    return Get-NormalizedPath $scriptPath
}

function Assert-NoProtectedOverlap($InstallRoot) {
    $protectedPaths = @($PluginPaths) + @($MarketplacePaths) + @($ConfigPaths) + @($CachePaths)
    foreach ($protected in $protectedPaths) {
        if (
            (Test-SameOrDescendantPath $protected $InstallRoot) -or
            (Test-SameOrDescendantPath $InstallRoot $protected)
        ) {
            throw "Legacy-root пересекается с защищённым путём: '$protected'."
        }
    }
}

function Assert-SafeRootBoundary($InstallRoot) {
    if (-not [System.IO.Path]::IsPathRooted($InstallRoot)) {
        throw "Legacy-root не является абсолютным путём."
    }
    $fullRoot = Get-NormalizedPath $InstallRoot
    $driveRoot = (Get-NormalizedPath ([System.IO.Path]::GetPathRoot($fullRoot)))
    if (Test-SamePath $fullRoot $driveRoot) {
        throw "Нельзя удалять корень диска."
    }
    if ($UserHome -and (Test-SamePath $fullRoot $UserHome)) {
        throw "Нельзя удалять домашнюю директорию пользователя."
    }
    if ($env:LOCALAPPDATA -and (Test-SamePath $fullRoot $env:LOCALAPPDATA)) {
        throw "Нельзя удалять LOCALAPPDATA целиком."
    }
    if (-not $UserHome -or -not (Test-SameOrDescendantPath $fullRoot $UserHome)) {
        throw "Legacy-root находится вне домашней директории пользователя."
    }
    if ([System.IO.Path]::GetFileName($fullRoot) -cne "CodexTeamSkills") {
        throw "Legacy-root не заканчивается точным именем CodexTeamSkills."
    }
    if (Test-SamePath (Split-Path $fullRoot -Parent) $UserHome) {
        throw "Legacy-root расположен слишком близко к корню домашней директории."
    }
    Assert-NoProtectedOverlap $fullRoot
}

function Assert-OwnedLegacyRoot($InstallRoot, $ExpectedActionPath) {
    $fullRoot = Get-NormalizedPath $InstallRoot
    Assert-SafeRootBoundary $fullRoot
    if (-not (Test-Path -LiteralPath $fullRoot -PathType Container)) {
        throw "Legacy-root из Scheduled Task отсутствует: '$fullRoot'."
    }

    $allEntries = @(Get-Item -LiteralPath $fullRoot -Force) + @(
        Get-ChildItem -LiteralPath $fullRoot -Force -Recurse
    )
    foreach ($entry in $allEntries) {
        if (Test-ReparsePoint $entry) {
            throw "В legacy-root обнаружен symlink/reparse point: '$($entry.FullName)'."
        }
        if (
            $entry.Name -like "*.backup.*" -or
            $entry.Name -like "*.previous.*" -or
            $entry.Name -like "*.stale.*"
        ) {
            throw "В legacy-root обнаружена recovery-копия, которую cleanup не имеет права удалять: '$($entry.FullName)'."
        }
    }

    foreach ($entry in @(Get-ChildItem -LiteralPath $fullRoot -Force)) {
        if ($AllowedRootEntries -inotcontains $entry.Name) {
            throw "В legacy-root обнаружен неизвестный объект верхнего уровня: '$($entry.Name)'."
        }
    }

    $binPath = Join-Path $fullRoot "bin"
    if (-not (Test-Path -LiteralPath $binPath -PathType Container)) {
        if ($ExpectedActionPath) {
            throw "В legacy-root из Scheduled Task отсутствует ожидаемая директория bin."
        }
        return @()
    }
    foreach ($entry in @(Get-ChildItem -LiteralPath $binPath -Force)) {
        if (-not $entry.PSIsContainer) {
            if ($AllowedBinEntries -inotcontains $entry.Name) {
                throw "В bin обнаружен неизвестный объект: '$($entry.Name)'."
            }
            continue
        }

        if ($entry.Name -cne $AllowedBinDirectory -or -not ($entry -is [System.IO.DirectoryInfo])) {
            throw "В bin обнаружен неизвестный объект: '$($entry.Name)'."
        }

        foreach ($bytecode in @(Get-ChildItem -LiteralPath $entry.FullName -Force)) {
            if (
                $bytecode.PSIsContainer -or
                -not ($bytecode -is [System.IO.FileInfo]) -or
                (Test-ReparsePoint $bytecode) -or
                $bytecode.Name -cnotmatch $AllowedRegistryBytecodePattern
            ) {
                throw "В __pycache__ обнаружен неизвестный объект: '$($bytecode.Name)'."
            }
        }
    }

    $markers = @($MarkerScripts | Where-Object { Test-Path -LiteralPath (Join-Path $binPath $_) -PathType Leaf })
    if ($ExpectedActionPath) {
        $actionName = [System.IO.Path]::GetFileName($ExpectedActionPath)
        if ($AllowedActionScripts -inotcontains $actionName) {
            throw "Scheduled Task ссылается на неизвестный скрипт '$actionName'."
        }
        if (-not (Test-SamePath (Split-Path $ExpectedActionPath -Parent) $binPath)) {
            throw "Scheduled Task ссылается на скрипт вне подтверждённой директории bin."
        }
        if (-not (Test-Path -LiteralPath $ExpectedActionPath -PathType Leaf)) {
            throw "Скрипт из Scheduled Task отсутствует: '$ExpectedActionPath'."
        }
    }
    return @($markers | Sort-Object)
}

function Get-Discovery() {
    $tasks = @(Get-TargetTasks)
    if ($tasks.Count -gt 1) {
        throw "Найдено несколько Scheduled Task с именем '$TaskName'."
    }
    if ($tasks.Count -eq 1) {
        $scriptPath = Get-TaskScriptPath $tasks[0]
        $binPath = Split-Path $scriptPath -Parent
        if ([System.IO.Path]::GetFileName($binPath) -ine "bin") {
            throw "Скрипт Scheduled Task находится не в директории bin."
        }
        $root = Get-NormalizedPath (Split-Path $binPath -Parent)
        $markers = Assert-OwnedLegacyRoot $root $scriptPath
        return [pscustomobject]@{
            Found = $true
            Source = "scheduled-task"
            Task = $tasks[0]
            TaskCount = 1
            Root = $root
            ActionScript = $scriptPath
            Markers = @($markers)
        }
    }

    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        throw "LOCALAPPDATA не определён; канонический fallback-path проверить невозможно."
    }
    $canonicalRoot = Get-NormalizedPath (Join-Path $env:LOCALAPPDATA "CodexTeamSkills")
    Assert-SafeRootBoundary $canonicalRoot
    if (-not (Test-Path -LiteralPath $canonicalRoot)) {
        return [pscustomobject]@{
            Found = $false
            Source = "not-found"
            Task = $null
            TaskCount = 0
            Root = $canonicalRoot
            ActionScript = $null
            Markers = @()
        }
    }
    $markers = @(Assert-OwnedLegacyRoot $canonicalRoot $null)
    $hasUpdate = $markers -icontains "update-team-skills.ps1"
    $hasLauncher = (
        $markers -icontains "bootstrap-team-skills.ps1" -or
        $markers -icontains "team-skills-auto-update-with-git-fallback.ps1"
    )
    if ($markers.Count -eq 0) {
        return [pscustomobject]@{
            Found = $false
            Source = "not-found"
            Task = $null
            TaskCount = 0
            Root = $canonicalRoot
            ActionScript = $null
            Markers = @()
        }
    }
    if (-not $hasUpdate -or -not $hasLauncher) {
        throw "Canonical updater-root содержит неполный или неоднозначный набор updater-маркеров."
    }
    return [pscustomobject]@{
        Found = $true
        Source = "canonical-fallback"
        Task = $null
        TaskCount = 0
        Root = $canonicalRoot
        ActionScript = $null
        Markers = @($markers)
    }
}

function Get-FileArgumentFromCommandLine($CommandLine) {
    if ([string]::IsNullOrWhiteSpace($CommandLine)) {
        return $null
    }
    $pattern = '(?i)(?:^|\s)-File\s+(?:"([^"]+)"|''([^'']+)''|(\S+))'
    $match = [System.Text.RegularExpressions.Regex]::Match($CommandLine, $pattern)
    if (-not $match.Success) {
        return $null
    }
    return @($match.Groups[1].Value, $match.Groups[2].Value, $match.Groups[3].Value) |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
        Select-Object -First 1
}

function Get-ExactUpdaterProcesses($InstallRoot) {
    $binPath = Join-Path $InstallRoot "bin"
    $allowedTargets = @($AllowedProcessScripts | ForEach-Object { Get-NormalizedPath (Join-Path $binPath $_) })
    $result = New-Object System.Collections.Generic.List[object]
    foreach ($process in @(Get-CimInstance Win32_Process -ErrorAction Stop)) {
        if ($process.Name -ine "powershell.exe" -and $process.Name -ine "pwsh.exe") {
            continue
        }
        $fileArgument = Get-FileArgumentFromCommandLine ([string]$process.CommandLine)
        if (-not $fileArgument -or -not [System.IO.Path]::IsPathRooted($fileArgument)) {
            continue
        }
        try {
            $target = Get-NormalizedPath $fileArgument
        } catch {
            continue
        }
        if (@($allowedTargets | Where-Object { Test-SamePath $_ $target }).Count -eq 1) {
            $result.Add([pscustomobject]@{
                Id = [int]$process.ProcessId
                Name = [string]$process.Name
                Target = $target
            })
        }
    }
    return $result.ToArray()
}

function Wait-ForExactUpdaterProcesses($InstallRoot, [int]$TimeoutSeconds) {
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        do {
            $remaining = @(Get-ExactUpdaterProcesses $InstallRoot)
            if ($remaining.Count -eq 0) {
                return @()
            }
            Start-Sleep -Milliseconds 250
        } while ($watch.Elapsed.TotalSeconds -lt $TimeoutSeconds)
        return @(Get-ExactUpdaterProcesses $InstallRoot)
    } finally {
        $watch.Stop()
    }
}

function New-Evidence($TaskCount, $ProcessCount, $RootPresent, $Protected) {
    return [pscustomobject]@{
        TaskCount = $TaskCount
        ProcessCount = $ProcessCount
        RootPresent = $RootPresent
        Protected = $Protected
    }
}

function Write-Report($Before, $After, $Outcome, $Reason) {
    Write-Host ""
    Write-Host ("{0,-24} {1,-66} {2,-66}" -f "Проверка", "Before", "After")
    Write-Host ("{0,-24} {1,-66} {2,-66}" -f ("-" * 24), ("-" * 66), ("-" * 66))
    Write-Host ("{0,-24} {1,-66} {2,-66}" -f "Scheduler", $Before.TaskCount, $After.TaskCount)
    Write-Host ("{0,-24} {1,-66} {2,-66}" -f "Updater processes", $Before.ProcessCount, $After.ProcessCount)
    Write-Host ("{0,-24} {1,-66} {2,-66}" -f "Updater root", $Before.RootPresent, $After.RootPresent)
    Write-Host ("{0,-24} {1,-66} {2,-66}" -f "Plugin hash", $Before.Protected.Plugin, $After.Protected.Plugin)
    Write-Host ("{0,-24} {1,-66} {2,-66}" -f "Marketplace hash", $Before.Protected.Marketplace, $After.Protected.Marketplace)
    Write-Host ("{0,-24} {1,-66} {2,-66}" -f "Config hash", $Before.Protected.Config, $After.Protected.Config)
    Write-Host ("{0,-24} {1,-66} {2,-66}" -f "Active cache hash", $Before.Protected.Cache, $After.Protected.Cache)
    Write-Host ""
    Write-Host "[team-skills] Результат: $Outcome"
    if ($Reason) {
        Write-Host "[team-skills] Причина: $Reason"
    }
}

function Get-UnknownEvidence($Protected) {
    return New-Evidence "UNKNOWN" "UNKNOWN" "UNKNOWN" $Protected
}

$protectedBefore = $null
try {
    $protectedBefore = Get-ProtectedFingerprints
} catch {
    $emptyProtected = [pscustomobject]@{
        Plugin = "UNKNOWN"
        Marketplace = "UNKNOWN"
        Config = "UNKNOWN"
        Cache = "UNKNOWN"
    }
    $unknown = Get-UnknownEvidence $emptyProtected
    Write-Report $unknown $unknown "REFUSED_UNSAFE" "Не удалось измерить защищённые артефакты: $($_.Exception.Message)"
    exit 3
}

try {
    $discovery = Get-Discovery
} catch {
    $unknown = Get-UnknownEvidence $protectedBefore
    Write-Report $unknown $unknown "REFUSED_UNSAFE" $_.Exception.Message
    exit 3
}

if (-not $discovery.Found) {
    $rootBefore = Test-Path -LiteralPath $discovery.Root
    try {
        $protectedAfter = Get-ProtectedFingerprints
        $rootAfter = Test-Path -LiteralPath $discovery.Root
    } catch {
        $unknown = Get-UnknownEvidence $protectedBefore
        Write-Report $unknown $unknown "REFUSED_UNSAFE" "Не удалось завершить повторное измерение: $($_.Exception.Message)"
        exit 3
    }
    $before = New-Evidence 0 0 $rootBefore $protectedBefore
    $after = New-Evidence 0 0 $rootAfter $protectedAfter
    if (-not (Test-ProtectedFingerprintsEqual $protectedBefore $protectedAfter)) {
        Write-Report $before $after "REFUSED_UNSAFE" "Защищённые артефакты изменились во время проверки."
        exit 3
    }
    $notFoundReason = if ($rootBefore) {
        "Scheduled Task отсутствует, а канонический путь не содержит полного набора updater-маркеров; путь не удалён."
    } else {
        "Legacy Scheduled Task и канонический updater-root отсутствуют."
    }
    Write-Report $before $after "NOT_FOUND" $notFoundReason
    exit 0
}

try {
    $processesBefore = @(Get-ExactUpdaterProcesses $discovery.Root)
} catch {
    $unknown = Get-UnknownEvidence $protectedBefore
    Write-Report $unknown $unknown "REFUSED_UNSAFE" "Не удалось проверить updater-процессы: $($_.Exception.Message)"
    exit 3
}

$before = New-Evidence $discovery.TaskCount $processesBefore.Count $true $protectedBefore
Write-Info "Источник attribution: $($discovery.Source)."
if ($discovery.Task) {
    Write-Info "Scheduled Task: $TaskPath$TaskName"
    Write-Info "Action script: $($discovery.ActionScript)"
} else {
    Write-Info "Scheduled Task: NOT_FOUND"
}
Write-Info "Legacy updater-root: $($discovery.Root)"
Write-Info "Updater-маркеры: $($discovery.Markers -join ', ')"
if ($processesBefore.Count -gt 0) {
    foreach ($process in $processesBefore) {
        Write-Info "Updater process: PID=$($process.Id), script=$($process.Target)"
    }
} else {
    Write-Info "Updater processes: 0"
}

if ($DryRun) {
    try {
        $processesAfter = @(Get-ExactUpdaterProcesses $discovery.Root)
        $protectedAfter = Get-ProtectedFingerprints
        $taskCountAfter = @(Get-TargetTasks).Count
        $rootAfter = Test-Path -LiteralPath $discovery.Root
        $after = New-Evidence $taskCountAfter $processesAfter.Count $rootAfter $protectedAfter
        if (-not (Test-ProtectedFingerprintsEqual $protectedBefore $protectedAfter)) {
            Write-Report $before $after "REFUSED_UNSAFE" "Защищённые артефакты изменились во время dry-run."
            exit 3
        }
        Write-Report $before $after "DRY_RUN_SAFE" "Мутаций не выполнялось. Для удаления запустите скрипт заново с -Apply."
        exit 0
    } catch {
        $unknown = Get-UnknownEvidence $protectedBefore
        Write-Report $before $unknown "REFUSED_UNSAFE" "Dry-run не завершил повторную проверку: $($_.Exception.Message)"
        exit 3
    }
}

try {
    # Apply никогда не доверяет discovery, выполненному ранее в этом процессе:
    # объект мог измениться между отчётом Before и первой мутацией.
    $confirmedDiscovery = Get-Discovery
    if (-not $confirmedDiscovery.Found) {
        throw "Apply preflight изменился: ранее найденная updater-инфраструктура больше не подтверждается."
    }
    if ($confirmedDiscovery.Source -cne $discovery.Source) {
        throw "Apply preflight изменился: источник attribution больше не совпадает."
    }
    if (-not (Test-SamePath $confirmedDiscovery.Root $discovery.Root)) {
        throw "Apply preflight изменился: updater-root больше не совпадает."
    }
    $oldActionMissing = [string]::IsNullOrWhiteSpace([string]$discovery.ActionScript)
    $newActionMissing = [string]::IsNullOrWhiteSpace([string]$confirmedDiscovery.ActionScript)
    if ($oldActionMissing -xor $newActionMissing) {
        throw "Apply preflight изменился: action Scheduled Task появился или исчез."
    }
    if (-not $oldActionMissing -and -not (Test-SamePath $confirmedDiscovery.ActionScript $discovery.ActionScript)) {
        throw "Apply preflight изменился: action Scheduled Task больше не совпадает."
    }
    $discovery = $confirmedDiscovery

    if ($discovery.Task) {
        Disable-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -ErrorAction Stop | Out-Null
        $tasksAfterDisable = @(Get-TargetTasks)
        if ($tasksAfterDisable.Count -ne 1 -or $tasksAfterDisable[0].TaskPath -cne $TaskPath) {
            throw "После Disable не удалось повторно подтвердить точную Scheduled Task."
        }
        if ([string]$tasksAfterDisable[0].State -eq "Running") {
            Stop-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -ErrorAction Stop
        }
    }

    $remaining = @(Wait-ForExactUpdaterProcesses $discovery.Root 10)
    foreach ($candidate in $remaining) {
        $confirmed = @(Get-ExactUpdaterProcesses $discovery.Root | Where-Object { $_.Id -eq $candidate.Id })
        if ($confirmed.Count -eq 1) {
            Stop-Process -Id $candidate.Id -Force -ErrorAction Stop
        }
    }
    $remaining = @(Wait-ForExactUpdaterProcesses $discovery.Root 5)
    if ($remaining.Count -gt 0) {
        throw "После ограниченного ожидания остались точные updater-процессы: $($remaining.Id -join ', ')."
    }

    if ($discovery.Task) {
        Unregister-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -Confirm:$false -ErrorAction Stop
    }

    Remove-Item -LiteralPath $discovery.Root -Recurse -Force -ErrorAction Stop

    $tasksAfter = @(Get-TargetTasks)
    $processesAfter = @(Get-ExactUpdaterProcesses $discovery.Root)
    $protectedAfter = Get-ProtectedFingerprints
    $rootAfter = Test-Path -LiteralPath $discovery.Root
    $after = New-Evidence $tasksAfter.Count $processesAfter.Count $rootAfter $protectedAfter

    if ($tasksAfter.Count -ne 0 -or $processesAfter.Count -ne 0 -or $rootAfter) {
        throw "Postcondition не достигнут: scheduler/process/root должны отсутствовать."
    }
    if (-not (Test-ProtectedFingerprintsEqual $protectedBefore $protectedAfter)) {
        throw "Хэш защищённого plugin, marketplace, config или active cache изменился."
    }

    Write-Report $before $after "CLEANED" "Удалена только доказанная legacy-инфраструктура автообновления."
    exit 0
} catch {
    $reason = $_.Exception.Message
    try {
        $taskCountAfter = @(Get-TargetTasks).Count
    } catch {
        $taskCountAfter = "UNKNOWN"
    }
    try {
        $processCountAfter = @(Get-ExactUpdaterProcesses $discovery.Root).Count
    } catch {
        $processCountAfter = "UNKNOWN"
    }
    try {
        $rootAfter = Test-Path -LiteralPath $discovery.Root
    } catch {
        $rootAfter = "UNKNOWN"
    }
    try {
        $protectedAfter = Get-ProtectedFingerprints
    } catch {
        $protectedAfter = [pscustomobject]@{
            Plugin = "UNKNOWN"
            Marketplace = "UNKNOWN"
            Config = "UNKNOWN"
            Cache = "UNKNOWN"
        }
    }
    $after = New-Evidence $taskCountAfter $processCountAfter $rootAfter $protectedAfter
    Write-Report $before $after "INCOMPLETE" $reason
    exit 4
}
