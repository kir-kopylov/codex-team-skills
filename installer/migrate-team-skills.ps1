param(
    [switch]$ValidateOnly,
    [Parameter(ValueFromRemainingArguments = $true)]
    [object[]]$UnexpectedArguments
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$BakedReleaseTag = "__TEAM_SKILLS_RELEASE_TAG__"
$PluginName = "team-skills"
$MarketplaceName = "codex-team-skills"

$ExitInvalidInvocation = 2
$ExitRefusedUnsafe = 3
$ExitCleanupIncomplete = 4
$ExitInstallPending = 5
$ExitInstallerRegression = 6
$ExitBlockedPreflight = 10
$ChildTimeoutMilliseconds = 600000
$ChildOutputMaxCharacters = 1048576
$ChildPollMilliseconds = 100

function Write-Info($Message) {
    Write-Host "[team-skills] $Message"
}

function New-MigrationOutcome($Result, $ExitCode, $Message) {
    return [pscustomobject]@{
        Result = [string]$Result
        ExitCode = [int]$ExitCode
        Message = [string]$Message
    }
}

function Write-FinalOutcome($Outcome) {
    if (-not [string]::IsNullOrWhiteSpace($Outcome.Message)) {
        Write-Info $Outcome.Message
    }
    Write-Host "TEAM_SKILLS_MIGRATION_RESULT=$($Outcome.Result)"
}

if ($UnexpectedArguments -and $UnexpectedArguments.Count -gt 0) {
    $invalid = New-MigrationOutcome "INVALID_INVOCATION" $ExitInvalidInvocation (
        "Неизвестные аргументы: $($UnexpectedArguments -join ' '). Использование: .\migrate-team-skills.ps1 [-ValidateOnly]"
    )
    Write-FinalOutcome $invalid
    exit $invalid.ExitCode
}

if ($ValidateOnly) {
    Write-Info "ValidateOnly: migrate-team-skills.ps1 разобран без перехода и без сетевых запросов."
    Write-Host "TEAM_SKILLS_MIGRATION_RESULT=VALIDATED"
    exit 0
}

function Get-NormalizedPath($Path) {
    if ([string]::IsNullOrWhiteSpace([string]$Path)) {
        throw "Получен пустой путь."
    }
    return [System.IO.Path]::GetFullPath([string]$Path).TrimEnd([char[]]"\/")
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

function Assert-NoReparsePointInExistingPath($Path, $HomePath, $Label) {
    $fullPath = Get-NormalizedPath $Path
    if (-not (Test-SameOrDescendantPath $fullPath $HomePath)) {
        throw "$Label находится вне текущего домашнего каталога: $fullPath"
    }

    $relative = $fullPath.Substring($HomePath.Length).TrimStart([char[]]"\/")
    $cursor = $HomePath
    if (Test-Path -LiteralPath $cursor) {
        $homeItem = Get-Item -LiteralPath $cursor -Force
        if (Test-ReparsePoint $homeItem) {
            throw "$Label проходит через reparse point: $cursor"
        }
    }
    foreach ($part in @($relative -split '[\\/]' | Where-Object { $_ })) {
        $cursor = Join-Path $cursor $part
        if (-not (Test-Path -LiteralPath $cursor)) {
            break
        }
        $item = Get-Item -LiteralPath $cursor -Force
        if (Test-ReparsePoint $item) {
            throw "$Label проходит через reparse point: $cursor"
        }
    }
}

function Assert-Preflight {
    if ($PSVersionTable.PSEdition -ne "Desktop" -or $PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -lt 1) {
        throw "Нужен Windows PowerShell 5.1; PowerShell Core и другие версии не поддерживаются этим переходом."
    }
    if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
        throw "Этот файл предназначен только для нативной Windows."
    }
    if ($BakedReleaseTag -notmatch '^team-skills-vr[0-9]+\.[0-9]+-[0-9a-f]{7}$') {
        throw "В migrator не встроен корректный immutable release tag. Используйте release-asset."
    }

    $overrides = @(
        Get-ChildItem Env: | Where-Object { $_.Name -like "CODEX_TEAM_SKILLS_*" } | Sort-Object Name
    )
    if ($overrides.Count -gt 0) {
        throw "Перед переходом удалите переменные override: $($overrides.Name -join ', ')."
    }

    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object System.Security.Principal.WindowsPrincipal($identity)
    if ($principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Не запускайте migrator от администратора. Откройте обычный пользовательский Codex/terminal."
    }

    $homePath = Get-NormalizedPath $HOME
    $profilePath = Get-NormalizedPath $env:USERPROFILE
    $systemProfilePath = Get-NormalizedPath (
        [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::UserProfile)
    )
    if (-not (Test-SamePath $homePath $profilePath) -or -not (Test-SamePath $homePath $systemProfilePath)) {
        throw "HOME, USERPROFILE и системный профиль указывают на разные каталоги."
    }
    if (-not (Test-Path -LiteralPath $homePath -PathType Container)) {
        throw "Домашний каталог текущего пользователя не найден: $homePath"
    }
    $homeRoot = [System.IO.Path]::GetPathRoot($homePath)
    if (Test-SamePath $homePath $homeRoot) {
        throw "Корень диска нельзя использовать как домашний каталог."
    }

    $pluginPath = Join-Path $homePath "plugins\team-skills"
    $marketplacePath = Join-Path $homePath ".agents\plugins\marketplace.json"
    $configPath = Join-Path $homePath ".codex\config.toml"
    $cachePath = Join-Path $homePath ".codex\plugins\cache\codex-team-skills"
    Assert-NoReparsePointInExistingPath $pluginPath $homePath "Plugin path"
    Assert-NoReparsePointInExistingPath $marketplacePath $homePath "Marketplace path"
    Assert-NoReparsePointInExistingPath $configPath $homePath "Codex config path"
    Assert-NoReparsePointInExistingPath $cachePath $homePath "Codex cache path"

    return [pscustomobject]@{
        Home = $homePath
        Plugin = $pluginPath
        Cache = $cachePath
    }
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

function Enter-MigrationMutex($HomePath) {
    $sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $suffix = (Get-TextSha256 "$sid|$HomePath").Substring(0, 24)
    $mutexName = "Global\CodexTeamSkillsMigration-$suffix"
    $mutex = New-Object -TypeName System.Threading.Mutex -ArgumentList @($false, $mutexName)
    $acquired = $false
    try {
        try {
            $acquired = $mutex.WaitOne(0)
        } catch [System.Threading.AbandonedMutexException] {
            $acquired = $true
        }
        if (-not $acquired) {
            throw "Для этого пользователя уже запущен другой migrator."
        }
        return $mutex
    } catch {
        if (-not $acquired) {
            $mutex.Dispose()
        }
        throw
    }
}

function Ensure-Directory($Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Download-File($Url, $Destination) {
    $lastMessage = ""
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Remove-Item -LiteralPath $Destination -Force -ErrorAction SilentlyContinue
            Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Destination -TimeoutSec 60
            if (-not (Test-Path -LiteralPath $Destination -PathType Leaf)) {
                throw "скачанный файл не найден"
            }
            if ((Get-Item -LiteralPath $Destination).Length -le 0) {
                throw "скачанный файл пуст"
            }
            return
        } catch {
            $lastMessage = $_.Exception.Message
            if ($attempt -lt 3) {
                Start-Sleep -Seconds $attempt
            }
        }
    }
    throw "Не удалось скачать release-asset после трёх попыток: $lastMessage"
}

function Assert-PowerShellScriptParseable($Path) {
    $tokens = $null
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile($Path, [ref]$tokens, [ref]$errors) | Out-Null
    if ($errors.Count -gt 0) {
        $messages = @($errors | ForEach-Object { $_.Message })
        throw "Скачанный PowerShell asset не разбирается: $($messages -join '; ')"
    }
}

function Initialize-ChildJobType {
    if ("CodexTeamSkillsMigration.NativeJob" -as [type]) {
        return
    }

    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;

namespace CodexTeamSkillsMigration
{
    public sealed class BoundedTextCapture
    {
        private readonly StreamReader reader;
        private readonly int maximumCharacters;
        private readonly StringBuilder text = new StringBuilder();
        private volatile bool overflowed;

        private BoundedTextCapture(StreamReader reader, int maximumCharacters)
        {
            if (reader == null) throw new ArgumentNullException("reader");
            if (maximumCharacters <= 0) throw new ArgumentOutOfRangeException("maximumCharacters");
            this.reader = reader;
            this.maximumCharacters = maximumCharacters;
            Completion = DrainAsync();
        }

        public Task Completion { get; private set; }

        public bool Overflowed { get { return overflowed; } }

        public string Text
        {
            get
            {
                lock (text) return text.ToString();
            }
        }

        public static BoundedTextCapture Start(StreamReader reader, int maximumCharacters)
        {
            return new BoundedTextCapture(reader, maximumCharacters);
        }

        private async Task DrainAsync()
        {
            char[] buffer = new char[4096];
            int count;
            while ((count = await reader.ReadAsync(buffer, 0, buffer.Length).ConfigureAwait(false)) > 0)
            {
                lock (text)
                {
                    int remaining = maximumCharacters - text.Length;
                    if (remaining > 0)
                    {
                        text.Append(buffer, 0, Math.Min(remaining, count));
                    }
                    if (count > remaining)
                    {
                        overflowed = true;
                    }
                }
            }
        }
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct JobObjectBasicLimitInformation
    {
        public long PerProcessUserTimeLimit;
        public long PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize;
        public UIntPtr MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass;
        public uint SchedulingClass;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct IoCounters
    {
        public ulong ReadOperationCount;
        public ulong WriteOperationCount;
        public ulong OtherOperationCount;
        public ulong ReadTransferCount;
        public ulong WriteTransferCount;
        public ulong OtherTransferCount;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct JobObjectExtendedLimitInformation
    {
        public JobObjectBasicLimitInformation BasicLimitInformation;
        public IoCounters IoInfo;
        public UIntPtr ProcessMemoryLimit;
        public UIntPtr JobMemoryLimit;
        public UIntPtr PeakProcessMemoryUsed;
        public UIntPtr PeakJobMemoryUsed;
    }

    public static class NativeJob
    {
        private const int JobObjectExtendedLimitInformationClass = 9;
        private const uint JobObjectLimitKillOnJobClose = 0x00002000;

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern IntPtr CreateJobObject(IntPtr jobAttributes, string name);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool SetInformationJobObject(
            IntPtr job,
            int informationClass,
            IntPtr information,
            uint informationLength
        );

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool CloseHandle(IntPtr handle);

        public static IntPtr CreateKillOnClose()
        {
            IntPtr job = CreateJobObject(IntPtr.Zero, null);
            if (job == IntPtr.Zero)
            {
                throw new Win32Exception(Marshal.GetLastWin32Error(), "CreateJobObject failed");
            }

            JobObjectExtendedLimitInformation limits = new JobObjectExtendedLimitInformation();
            limits.BasicLimitInformation.LimitFlags = JobObjectLimitKillOnJobClose;
            int size = Marshal.SizeOf(typeof(JobObjectExtendedLimitInformation));
            IntPtr pointer = Marshal.AllocHGlobal(size);
            try
            {
                Marshal.StructureToPtr(limits, pointer, false);
                if (!SetInformationJobObject(job, JobObjectExtendedLimitInformationClass, pointer, (uint)size))
                {
                    throw new Win32Exception(Marshal.GetLastWin32Error(), "SetInformationJobObject failed");
                }
                return job;
            }
            catch
            {
                CloseHandle(job);
                throw;
            }
            finally
            {
                Marshal.FreeHGlobal(pointer);
            }
        }

        public static void Assign(IntPtr job, IntPtr process)
        {
            if (!AssignProcessToJobObject(job, process))
            {
                throw new Win32Exception(Marshal.GetLastWin32Error(), "AssignProcessToJobObject failed");
            }
        }

        public static void Close(IntPtr job)
        {
            if (job != IntPtr.Zero)
            {
                CloseHandle(job);
            }
        }
    }
}
'@
}

function Invoke-ChildPowerShell($ScriptPath, [string[]]$Arguments, $WorkingDirectory) {
    $argumentParts = @()
    foreach ($argument in @($Arguments)) {
        if ($argument -match '^-[A-Za-z][A-Za-z0-9]*$') {
            $argumentParts += $argument
        } else {
            $argumentParts += "'" + ([string]$argument).Replace("'", "''") + "'"
        }
    }

    $escapedPath = ([System.IO.Path]::GetFullPath($ScriptPath)).Replace("'", "''")
    $gatePath = Join-Path $WorkingDirectory ("child-gate-" + [guid]::NewGuid().ToString("N") + ".ready")
    $escapedGatePath = $gatePath.Replace("'", "''")
    $argumentText = ($argumentParts -join " ")
    $command = @"
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding(`$false)
`$gateDeadline = [DateTime]::UtcNow.AddSeconds(30)
while (-not (Test-Path -LiteralPath '$escapedGatePath' -PathType Leaf)) {
    if ([DateTime]::UtcNow -ge `$gateDeadline) { exit 90 }
    Start-Sleep -Milliseconds 50
}
& '$escapedPath' $argumentText
if (`$null -eq `$LASTEXITCODE) { exit 1 }
exit `$LASTEXITCODE
"@
    $encodedCommand = [System.Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($command))

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = Join-Path $PSHOME "powershell.exe"
    $startInfo.Arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand $encodedCommand"
    $startInfo.WorkingDirectory = $WorkingDirectory
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    $startInfo.StandardOutputEncoding = $utf8
    $startInfo.StandardErrorEncoding = $utf8

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    $started = $false
    $jobHandle = [IntPtr]::Zero
    try {
        Initialize-ChildJobType
        $jobHandle = [CodexTeamSkillsMigration.NativeJob]::CreateKillOnClose()
        if (-not $process.Start()) {
            throw "Не удалось запустить child PowerShell."
        }
        $started = $true
        [CodexTeamSkillsMigration.NativeJob]::Assign($jobHandle, $process.Handle)
        $stdoutCapture = [CodexTeamSkillsMigration.BoundedTextCapture]::Start(
            $process.StandardOutput,
            $ChildOutputMaxCharacters
        )
        $stderrCapture = [CodexTeamSkillsMigration.BoundedTextCapture]::Start(
            $process.StandardError,
            $ChildOutputMaxCharacters
        )
        [System.IO.File]::WriteAllText($gatePath, "go", [System.Text.Encoding]::ASCII)
        $deadline = [DateTime]::UtcNow.AddMilliseconds($ChildTimeoutMilliseconds)
        $rootCompleted = $false
        $outputExceeded = $false
        $captureFailed = $false
        do {
            if ($process.WaitForExit($ChildPollMilliseconds)) {
                $rootCompleted = $true
                break
            }
            if ($stdoutCapture.Overflowed -or $stderrCapture.Overflowed) {
                $outputExceeded = $true
                break
            }
            if ($stdoutCapture.Completion.IsFaulted -or $stderrCapture.Completion.IsFaulted) {
                $captureFailed = $true
                break
            }
        } while ([DateTime]::UtcNow -lt $deadline)

        $outputExceeded = $outputExceeded -or $stdoutCapture.Overflowed -or $stderrCapture.Overflowed
        $captureFailed = $captureFailed -or $stdoutCapture.Completion.IsFaulted -or $stderrCapture.Completion.IsFaulted

        # Closing a KILL_ON_JOB_CLOSE Job Object terminates the root and every descendant,
        # including descendants that inherited stdout/stderr handles.
        [CodexTeamSkillsMigration.NativeJob]::Close($jobHandle)
        $jobHandle = [IntPtr]::Zero

        if (-not $process.HasExited -and -not $process.WaitForExit(10000)) {
            throw "Windows Job Object не завершил child process tree за 10 секунд."
        }

        $outputTasks = [System.Threading.Tasks.Task[]]@(
            $stdoutCapture.Completion,
            $stderrCapture.Completion
        )
        if (-not [System.Threading.Tasks.Task]::WaitAll($outputTasks, 10000)) {
            throw "Child process завершился, но stdout/stderr не закрылись за 10 секунд."
        }
        $outputExceeded = $outputExceeded -or $stdoutCapture.Overflowed -or $stderrCapture.Overflowed
        $captureFailed = $captureFailed -or $stdoutCapture.Completion.IsFaulted -or $stderrCapture.Completion.IsFaulted
        if ($outputExceeded) {
            throw "Child process превысил лимит вывода $ChildOutputMaxCharacters символов на поток."
        }
        if ($captureFailed) {
            throw "Не удалось безопасно прочитать stdout/stderr child process."
        }
        if (-not $rootCompleted) {
            throw "Child PowerShell превысил timeout $([int]($ChildTimeoutMilliseconds / 1000)) секунд."
        }
        $stdout = $stdoutCapture.Text
        $stderr = $stderrCapture.Text
        $exitCode = $process.ExitCode
        return [pscustomobject]@{
            Stdout = [string]$stdout
            Stderr = [string]$stderr
            ExitCode = [int]$exitCode
        }
    } finally {
        if ($jobHandle -ne [IntPtr]::Zero) {
            [CodexTeamSkillsMigration.NativeJob]::Close($jobHandle)
            $jobHandle = [IntPtr]::Zero
        }
        Remove-Item -LiteralPath $gatePath -Force -ErrorAction SilentlyContinue
        if ($started) {
            try {
                if (-not $process.HasExited) {
                    $process.Kill()
                    $process.WaitForExit(10000) | Out-Null
                }
            } catch { }
        }
        $process.Dispose()
    }
}

function Write-ChildEvidence($Label, $Invocation) {
    Write-Info "$Label завершён с exit code $($Invocation.ExitCode)."
    if (-not [string]::IsNullOrEmpty($Invocation.Stdout)) {
        Write-Host -NoNewline $Invocation.Stdout
        if (-not $Invocation.Stdout.EndsWith("`n")) {
            Write-Host ""
        }
    }
    if (-not [string]::IsNullOrEmpty($Invocation.Stderr)) {
        Write-Host -NoNewline $Invocation.Stderr
        if (-not $Invocation.Stderr.EndsWith("`n")) {
            Write-Host ""
        }
    }
}

function Get-SingleProtocolValue($Text, $Name) {
    $pattern = "(?m)^" + [regex]::Escape($Name) + "=([^\r\n]+)\r?$"
    $matches = [regex]::Matches([string]$Text, $pattern)
    if ($matches.Count -ne 1) {
        throw "Child-script должен вывести ровно одну строку $Name=<value>; найдено: $($matches.Count)."
    }
    return $matches[0].Groups[1].Value
}

function Read-CleanupContract($Invocation) {
    $result = Get-SingleProtocolValue $Invocation.Stdout "TEAM_SKILLS_RESULT"
    $expectedExit = switch ($result) {
        "NOT_FOUND" { 0 }
        "DRY_RUN_SAFE" { 0 }
        "CLEANED" { 0 }
        "REFUSED_UNSAFE" { 3 }
        "INCOMPLETE" { 4 }
        "INVALID_INVOCATION" { 2 }
        default { -1 }
    }
    if ($expectedExit -lt 0 -or $Invocation.ExitCode -ne $expectedExit) {
        throw "Cleanup protocol не совпал: result=$result, exit=$($Invocation.ExitCode), expected=$expectedExit."
    }
    return $result
}

function Get-CleanupFailureOutcome($Result, $Phase, [bool]$MutationStarted = $false) {
    if ($Result -eq "REFUSED_UNSAFE" -and -not $MutationStarted) {
        return New-MigrationOutcome "REFUSED_UNSAFE" $ExitRefusedUnsafe "${Phase}: cleanup отказался работать с неоднозначным объектом."
    }
    return New-MigrationOutcome "CLEANUP_INCOMPLETE" $ExitCleanupIncomplete "${Phase}: cleanup не достиг доказанного результата."
}

function Assert-InstalledPlugin($Preflight, $ExpectedPluginVersion) {
    $pluginRootItem = Get-Item -LiteralPath $Preflight.Plugin -Force -ErrorAction Stop
    if (-not $pluginRootItem.PSIsContainer -or (Test-ReparsePoint $pluginRootItem)) {
        throw "Plugin root после installer должен быть обычной директорией."
    }
    $manifestPath = Join-Path $Preflight.Plugin ".codex-plugin\plugin.json"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "После installer не найден plugin manifest: $manifestPath"
    }
    $manifestItem = Get-Item -LiteralPath $manifestPath -Force
    if (Test-ReparsePoint $manifestItem) {
        throw "Plugin manifest не должен быть reparse point."
    }
    try {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    } catch {
        throw "Plugin manifest после installer не является валидным JSON: $($_.Exception.Message)"
    }
    if (
        $manifest.name -ne $PluginName -or
        $manifest.release_tag -ne $BakedReleaseTag -or
        [string]::IsNullOrWhiteSpace([string]$manifest.version) -or
        ([string]$manifest.version) -cne ([string]$ExpectedPluginVersion)
    ) {
        throw "Plugin manifest на диске не подтверждает exact release $BakedReleaseTag."
    }
    if (Test-Path -LiteralPath $Preflight.Cache) {
        throw "Codex plugin cache не удалён installer-ом: $($Preflight.Cache)"
    }
}

function Invoke-Migration {
    $mutex = $null
    $mutexAcquired = $false
    $workDir = $null
    $cleanupProven = $false
    $installerAttempted = $false

    try {
        try {
            Write-Info "Выполняю preflight без изменений установки."
            $preflight = Assert-Preflight
            $mutex = Enter-MigrationMutex $preflight.Home
            $mutexAcquired = $true

            $workDir = Join-Path ([System.IO.Path]::GetTempPath()) (
                "codex-team-skills-migrate-" + [guid]::NewGuid().ToString("N")
            )
            Ensure-Directory $workDir
            $releaseBase = "https://github.com/kir-kopylov/codex-team-skills/releases/download/$BakedReleaseTag"
            $cleanupScript = Join-Path $workDir "remove-team-skills-autoupdate.ps1"
            $installerScript = Join-Path $workDir "install-team-skills.ps1"
            Write-Info "Скачиваю cleanup и installer из exact release $BakedReleaseTag."
            Download-File "$releaseBase/remove-team-skills-autoupdate.ps1" $cleanupScript
            Download-File "$releaseBase/install-team-skills.ps1" $installerScript
            Assert-PowerShellScriptParseable $cleanupScript
            Assert-PowerShellScriptParseable $installerScript
        } catch {
            return New-MigrationOutcome "BLOCKED_PREFLIGHT" $ExitBlockedPreflight (
                "Переход не начат: $($_.Exception.Message)"
            )
        }

        Write-Info "Проверяю legacy-автообновление в режиме DryRun."
        try {
            $initialDryRun = Invoke-ChildPowerShell -ScriptPath $cleanupScript -Arguments @("-DryRun") -WorkingDirectory $workDir
            Write-ChildEvidence "Первый cleanup DryRun" $initialDryRun
            $initialResult = Read-CleanupContract $initialDryRun
        } catch {
            return New-MigrationOutcome "CLEANUP_INCOMPLETE" $ExitCleanupIncomplete (
                "Первый cleanup DryRun не дал валидного машинного результата: $($_.Exception.Message)"
            )
        }

        if ($initialResult -eq "REFUSED_UNSAFE" -or $initialResult -eq "INCOMPLETE" -or $initialResult -eq "INVALID_INVOCATION") {
            return Get-CleanupFailureOutcome $initialResult "Первый DryRun"
        }
        if ($initialResult -ne "NOT_FOUND" -and $initialResult -ne "DRY_RUN_SAFE") {
            return New-MigrationOutcome "CLEANUP_INCOMPLETE" $ExitCleanupIncomplete (
                "Первый DryRun вернул недопустимое состояние: $initialResult."
            )
        }

        if ($initialResult -eq "DRY_RUN_SAFE") {
            Write-Info "DryRun доказал безопасный scope; запускаю cleanup Apply один раз."
            try {
                $initialApply = Invoke-ChildPowerShell -ScriptPath $cleanupScript -Arguments @("-Apply") -WorkingDirectory $workDir
                Write-ChildEvidence "Cleanup Apply" $initialApply
                $applyResult = Read-CleanupContract $initialApply
            } catch {
                return New-MigrationOutcome "CLEANUP_INCOMPLETE" $ExitCleanupIncomplete (
                    "Cleanup Apply не дал валидного машинного результата: $($_.Exception.Message)"
                )
            }
            if ($applyResult -eq "REFUSED_UNSAFE" -or $applyResult -eq "INCOMPLETE" -or $applyResult -eq "INVALID_INVOCATION") {
                return Get-CleanupFailureOutcome $applyResult "Cleanup Apply" $true
            }
            if ($applyResult -ne "CLEANED" -and $applyResult -ne "NOT_FOUND") {
                return New-MigrationOutcome "CLEANUP_INCOMPLETE" $ExitCleanupIncomplete (
                    "Cleanup Apply вернул недопустимое состояние: $applyResult."
                )
            }
        }
        $cleanupProven = $true

        Write-Info "Запускаю installer exact release один раз."
        $installerAttempted = $true
        try {
            $exactManifestUrl = "$releaseBase/manifest.json"
            $install = Invoke-ChildPowerShell -ScriptPath $installerScript -Arguments @(
                "-ManifestUrl",
                $exactManifestUrl
            ) -WorkingDirectory $workDir
            Write-ChildEvidence "Installer" $install
            $installResult = Get-SingleProtocolValue $install.Stdout "TEAM_SKILLS_RESULT"
            if ($install.ExitCode -ne 0 -or $installResult -ne "INSTALLED") {
                throw "result=$installResult, exit=$($install.ExitCode)"
            }
            $installedRelease = Get-SingleProtocolValue $install.Stdout "TEAM_SKILLS_RELEASE"
            if ($installedRelease -cne $BakedReleaseTag) {
                throw "installer сообщил release $installedRelease вместо $BakedReleaseTag"
            }
            $installedPluginVersion = Get-SingleProtocolValue $install.Stdout "TEAM_SKILLS_PLUGIN_VERSION"
            Assert-InstalledPlugin $preflight $installedPluginVersion
        } catch {
            return New-MigrationOutcome "LEGACY_REMOVED_INSTALL_PENDING" $ExitInstallPending (
                "Legacy updater отсутствует, но exact release не доказан на диске: $($_.Exception.Message)"
            )
        }

        Write-Info "Повторно проверяю, что installer не вернул автообновление."
        try {
            $finalDryRun = Invoke-ChildPowerShell -ScriptPath $cleanupScript -Arguments @("-DryRun") -WorkingDirectory $workDir
            Write-ChildEvidence "Финальный cleanup DryRun" $finalDryRun
            $finalResult = Read-CleanupContract $finalDryRun
        } catch {
            return New-MigrationOutcome "CLEANUP_INCOMPLETE" $ExitCleanupIncomplete (
                "Финальный cleanup DryRun не дал валидного машинного результата: $($_.Exception.Message)"
            )
        }

        if ($finalResult -eq "NOT_FOUND") {
            return New-MigrationOutcome "MIGRATED_RESTART_REQUIRED" 0 (
                "Exact release $BakedReleaseTag установлен на диске. Полностью перезапустите Codex."
            )
        }
        if ($finalResult -eq "DRY_RUN_SAFE") {
            Write-Info "После installer снова обнаружено legacy-автообновление; очищаю его и запрещаю успех rollout."
            try {
                $regressionApply = Invoke-ChildPowerShell -ScriptPath $cleanupScript -Arguments @("-Apply") -WorkingDirectory $workDir
                Write-ChildEvidence "Cleanup регрессии" $regressionApply
                $regressionResult = Read-CleanupContract $regressionApply
            } catch {
                return New-MigrationOutcome "CLEANUP_INCOMPLETE" $ExitCleanupIncomplete (
                    "Регрессия installer обнаружена, но cleanup не дал валидного результата: $($_.Exception.Message)"
                )
            }
            if ($regressionResult -eq "CLEANED" -or $regressionResult -eq "NOT_FOUND") {
                return New-MigrationOutcome "INSTALLER_REGRESSION_CLEANED" $ExitInstallerRegression (
                    "После installer обнаружен updater; updater снова удалён, но этот release нельзя раскатывать."
                )
            }
            return Get-CleanupFailureOutcome $regressionResult "Cleanup post-install регрессии" $true
        }
        if ($finalResult -eq "REFUSED_UNSAFE" -or $finalResult -eq "INCOMPLETE" -or $finalResult -eq "INVALID_INVOCATION") {
            return Get-CleanupFailureOutcome $finalResult "Финальный DryRun" $true
        }
        return New-MigrationOutcome "CLEANUP_INCOMPLETE" $ExitCleanupIncomplete (
            "Финальный DryRun вернул недопустимое состояние: $finalResult."
        )
    } catch {
        if ($installerAttempted -or $cleanupProven) {
            return New-MigrationOutcome "LEGACY_REMOVED_INSTALL_PENDING" $ExitInstallPending (
                "Переход остановлен после cleanup: $($_.Exception.Message)"
            )
        }
        return New-MigrationOutcome "BLOCKED_PREFLIGHT" $ExitBlockedPreflight (
            "Переход не начат: $($_.Exception.Message)"
        )
    } finally {
        if ($workDir -and (Test-Path -LiteralPath $workDir)) {
            Remove-Item -LiteralPath $workDir -Recurse -Force -ErrorAction SilentlyContinue
        }
        if ($mutex) {
            if ($mutexAcquired) {
                try { $mutex.ReleaseMutex() } catch { }
            }
            $mutex.Dispose()
        }
    }
}

$outcome = Invoke-Migration
Write-FinalOutcome $outcome
exit $outcome.ExitCode
