from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import ROOT


CMD = ROOT / "installer" / "migrate-team-skills.cmd"
PS1 = Path(
    os.environ.get(
        "TEAM_SKILLS_WINDOWS_MIGRATOR_SCRIPT",
        ROOT / "installer" / "migrate-team-skills.ps1",
    )
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def powershell_executable() -> str | None:
    return shutil.which("powershell.exe") or shutil.which("pwsh")


def test_windows_migration_entrypoints_are_release_bound_and_temp_only() -> None:
    cmd = read(CMD)
    ps1 = read(PS1)

    assert '__TEAM_SKILLS_RELEASE_TAG__' in cmd
    baked_match = re.search(r'^\$BakedReleaseTag = "([^"]+)"$', ps1, re.MULTILINE)
    assert baked_match
    baked_tag = baked_match.group(1)
    assert baked_tag == "__TEAM_SKILLS_RELEASE_TAG__" or re.fullmatch(
        r"team-skills-vr[0-9]+\.[0-9]+-[0-9a-f]{7}", baked_tag
    )
    assert "releases/download/%BAKED_RELEASE_TAG%/migrate-team-skills.ps1" in cmd
    assert "releases/download/$BakedReleaseTag" in ps1
    assert "releases/latest" not in cmd
    assert "releases/latest" not in ps1
    assert "%TEMP%\\migrate-team-skills-%RANDOM%-%RANDOM%.ps1" in cmd
    assert 'del /f /q "%PS_SCRIPT%"' in cmd
    assert "DOWNLOADED_MIGRATOR" not in cmd
    assert '"codex-team-skills-migrate-" + [guid]::NewGuid()' in ps1
    assert "Remove-Item -LiteralPath $workDir -Recurse -Force" in ps1


def test_cmd_always_downloads_exact_release_ps1_and_ignores_adjacent_files() -> None:
    cmd = read(CMD)

    download = cmd.index("Invoke-WebRequest")
    run = cmd.index('powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%PS_SCRIPT%"')
    assert download < run
    assert 'if not exist "%PS_SCRIPT%"' not in cmd
    assert "%~dp0" not in cmd
    assert "TEAM_SKILLS_MIGRATION_RESULT=BLOCKED_PREFLIGHT" in cmd
    assert "exit /b 10" in cmd


def test_ps1_preflight_is_windows_ps51_non_admin_and_canonical_home_only() -> None:
    text = read(PS1)

    for marker in (
        '$PSVersionTable.PSEdition -ne "Desktop"',
        "$PSVersionTable.PSVersion.Major -ne 5",
        "$PSVersionTable.PSVersion.Minor -lt 1",
        "[System.PlatformID]::Win32NT",
        "WindowsBuiltInRole]::Administrator",
        "Get-NormalizedPath $HOME",
        "Get-NormalizedPath $env:USERPROFILE",
        "SpecialFolder]::UserProfile",
        "Test-SamePath $homePath $profilePath",
        "Test-SamePath $homePath $systemProfilePath",
        "Assert-NoReparsePointInExistingPath",
    ):
        assert marker in text

    assert 'Get-ChildItem Env: | Where-Object { $_.Name -like "CODEX_TEAM_SKILLS_*" }' in text
    assert "CODEX_TEAM_SKILLS_PLUGIN_DIR" not in text
    assert "CODEX_TEAM_SKILLS_MANIFEST_URL" not in text


def test_ps1_uses_transient_per_user_named_mutex() -> None:
    text = read(PS1)

    assert "WindowsIdentity]::GetCurrent().User.Value" in text
    assert '"Global\\CodexTeamSkillsMigration-$suffix"' in text
    assert "$mutex.WaitOne(0)" in text
    assert "AbandonedMutexException" in text
    assert "$mutex.ReleaseMutex()" in text
    assert "$mutex.Dispose()" in text
    assert "Register-ScheduledTask" not in text
    assert "New-ScheduledTask" not in text


def test_ps1_downloads_exact_cleanup_and_installer_before_any_child_mutation() -> None:
    text = read(PS1)

    release_base = text.index(
        '$releaseBase = "https://github.com/kir-kopylov/codex-team-skills/releases/download/$BakedReleaseTag"'
    )
    cleanup_download = text.index(
        'Download-File "$releaseBase/remove-team-skills-autoupdate.ps1"', release_base
    )
    installer_download = text.index(
        'Download-File "$releaseBase/install-team-skills.ps1"', cleanup_download
    )
    parse_cleanup = text.index("Assert-PowerShellScriptParseable $cleanupScript", installer_download)
    first_child = text.index("Invoke-ChildPowerShell -ScriptPath $cleanupScript", parse_cleanup)

    assert release_base < cleanup_download < installer_download < parse_cleanup < first_child
    assert text.count("Invoke-ChildPowerShell -ScriptPath $installerScript") == 1
    assert '$exactManifestUrl = "$releaseBase/manifest.json"' in text
    assert '"-ManifestUrl",' in text


def test_child_stdout_and_exit_code_are_captured_from_one_process() -> None:
    text = read(PS1)

    start = text.index("function Invoke-ChildPowerShell")
    end = text.index("function Write-ChildEvidence", start)
    child = text[start:end]
    for marker in (
        "System.Diagnostics.ProcessStartInfo",
        "$startInfo.RedirectStandardOutput = $true",
        "$startInfo.RedirectStandardError = $true",
        "[CodexTeamSkillsMigration.BoundedTextCapture]::Start(",
        "$process.StandardOutput",
        "$process.StandardError",
        "$process.WaitForExit($ChildPollMilliseconds)",
        "$process.ExitCode",
        "Stdout = [string]$stdout",
        "Stderr = [string]$stderr",
        "ExitCode = [int]$exitCode",
    ):
        assert marker in child

    assert 'Get-SingleProtocolValue $Invocation.Stdout "TEAM_SKILLS_RESULT"' in text
    assert 'Get-SingleProtocolValue $install.Stdout "TEAM_SKILLS_RELEASE"' in text
    assert "$ChildTimeoutMilliseconds = 600000" in text
    assert "$ChildOutputMaxCharacters = 1048576" in text
    assert "$ChildPollMilliseconds = 100" in text
    for marker in (
        "public sealed class BoundedTextCapture",
        "maximumCharacters - text.Length",
        "overflowed = true",
        "function Initialize-ChildJobType",
        "JobObjectLimitKillOnJobClose",
        "CreateJobObject",
        "SetInformationJobObject",
        "AssignProcessToJobObject",
        "[CodexTeamSkillsMigration.NativeJob]::Assign($jobHandle, $process.Handle)",
        "[CodexTeamSkillsMigration.NativeJob]::Close($jobHandle)",
        "[System.Threading.Tasks.Task]::WaitAll($outputTasks, 10000)",
        "if (-not $process.HasExited -and -not $process.WaitForExit(10000))",
    ):
        assert marker in child or marker in text

    assignment = child.index(
        "[CodexTeamSkillsMigration.NativeJob]::Assign($jobHandle, $process.Handle)"
    )
    gate_release = child.index('[System.IO.File]::WriteAllText($gatePath, "go"')
    assert assignment < gate_release
    wait_all = child.index("[System.Threading.Tasks.Task]::WaitAll($outputTasks, 10000)")
    post_drain_overflow_check = child.index(
        "$outputExceeded = $outputExceeded -or $stdoutCapture.Overflowed", wait_all
    )
    assert wait_all < post_drain_overflow_check


def test_migration_flow_is_ordered_and_installer_is_not_retried() -> None:
    text = read(PS1)

    initial_dry_run = text.index(
        'Invoke-ChildPowerShell -ScriptPath $cleanupScript -Arguments @("-DryRun")'
    )
    conditional_apply = text.index('if ($initialResult -eq "DRY_RUN_SAFE")', initial_dry_run)
    initial_apply = text.index(
        'Invoke-ChildPowerShell -ScriptPath $cleanupScript -Arguments @("-Apply")',
        conditional_apply,
    )
    installer = text.index("Invoke-ChildPowerShell -ScriptPath $installerScript", initial_apply)
    disk_check = text.index("Assert-InstalledPlugin $preflight", installer)
    final_dry_run = text.index(
        'Invoke-ChildPowerShell -ScriptPath $cleanupScript -Arguments @("-DryRun")',
        disk_check,
    )

    assert initial_dry_run < conditional_apply < initial_apply < installer < disk_check < final_dry_run
    assert text.count("Invoke-ChildPowerShell -ScriptPath $installerScript") == 1
    assert 'if ($finalResult -eq "NOT_FOUND")' in text


def test_disk_verification_binds_plugin_to_release_and_requires_empty_cache() -> None:
    text = read(PS1)

    verification = text[
        text.index("function Assert-InstalledPlugin") : text.index("function Invoke-Migration")
    ]
    for marker in (
        '.codex-plugin\\plugin.json',
        "$manifest.name -ne $PluginName",
        "$manifest.release_tag -ne $BakedReleaseTag",
        "([string]$manifest.version) -cne ([string]$ExpectedPluginVersion)",
        "Plugin root после installer должен быть обычной директорией",
        "Test-Path -LiteralPath $Preflight.Cache",
        "Codex plugin cache не удалён installer-ом",
    ):
        assert marker in verification


def test_installer_regression_is_cleaned_but_never_reported_as_success() -> None:
    text = read(PS1)

    regression_gate = text.index('if ($finalResult -eq "DRY_RUN_SAFE")')
    regression_apply = text.index(
        'Invoke-ChildPowerShell -ScriptPath $cleanupScript -Arguments @("-Apply")',
        regression_gate,
    )
    regression_result = text.index('"INSTALLER_REGRESSION_CLEANED"', regression_apply)
    success = text.index('"MIGRATED_RESTART_REQUIRED"')

    assert success < regression_gate < regression_apply < regression_result
    assert '$ExitInstallerRegression = 6' in text
    assert '"INSTALLER_REGRESSION_CLEANED" $ExitInstallerRegression' in text
    assert 'Get-CleanupFailureOutcome $finalResult "Финальный DryRun" $true' in text
    assert 'Get-CleanupFailureOutcome $applyResult "Cleanup Apply" $true' in text


def test_migration_has_stable_terminal_results_and_shared_exit_contract() -> None:
    text = read(PS1)

    for result in (
        "BLOCKED_PREFLIGHT",
        "REFUSED_UNSAFE",
        "CLEANUP_INCOMPLETE",
        "LEGACY_REMOVED_INSTALL_PENDING",
        "INSTALLER_REGRESSION_CLEANED",
        "MIGRATED_RESTART_REQUIRED",
    ):
        assert result in text
    for marker in (
        "$ExitInvalidInvocation = 2",
        "$ExitRefusedUnsafe = 3",
        "$ExitCleanupIncomplete = 4",
        "$ExitInstallPending = 5",
        "$ExitInstallerRegression = 6",
        "$ExitBlockedPreflight = 10",
        'Write-Host "TEAM_SKILLS_MIGRATION_RESULT=$($Outcome.Result)"',
    ):
        assert marker in text


def test_migrator_does_not_create_persistent_state_or_logs() -> None:
    text = read(PS1)

    for forbidden in (
        "state.json",
        "last-repair.json",
        "Start-Transcript",
        "Register-ScheduledTask",
        "New-ScheduledTask",
        "CodexTeamSkills\\logs",
        "CodexTeamSkills\\state",
    ):
        assert forbidden not in text


@pytest.mark.skipif(powershell_executable() is None, reason="PowerShell недоступен")
def test_windows_migrator_parses_in_available_powershell() -> None:
    executable = powershell_executable()
    assert executable is not None
    literal_path = str(PS1).replace("'", "''")
    command = (
        "$tokens = $null; $errors = $null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{literal_path}', "
        "[ref]$tokens, [ref]$errors) | Out-Null; "
        "if ($errors.Count -gt 0) { $errors | ForEach-Object { Write-Error $_ }; exit 1 }"
    )

    result = subprocess.run(
        [executable, "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(powershell_executable() is None, reason="PowerShell недоступен")
def test_validate_only_has_no_network_or_product_mutation() -> None:
    executable = powershell_executable()
    assert executable is not None

    result = subprocess.run(
        [
            executable,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PS1),
            "-ValidateOnly",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "TEAM_SKILLS_MIGRATION_RESULT=VALIDATED" in result.stdout


@pytest.mark.skipif(
    os.name != "nt" or powershell_executable() is None,
    reason="Нужен Windows PowerShell для live orchestration",
)
def test_windows_orchestrator_runs_cleanup_install_and_final_check_once(tmp_path: Path) -> None:
    executable = powershell_executable()
    assert executable is not None
    source = read(PS1)
    baked_match = re.search(r'^\$BakedReleaseTag = "([^"]+)"$', source, re.MULTILINE)
    assert baked_match
    source_release_tag = baked_match.group(1)
    release_tag = (
        "team-skills-vr999.1-deadbee"
        if source_release_tag == "__TEAM_SKILLS_RELEASE_TAG__"
        else source_release_tag
    )
    definitions, separator, _ = source.partition("$outcome = Invoke-Migration")
    assert separator
    definitions = definitions.replace(source_release_tag, release_tag, 1)

    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    cache = home / ".codex" / "plugins" / "cache" / "codex-team-skills"
    cache.mkdir(parents=True)
    legacy_state = tmp_path / "legacy-present"
    legacy_state.write_text("legacy\n", encoding="utf-8")
    sequence = tmp_path / "sequence.log"

    cleanup_fixture = fixtures / "remove-team-skills-autoupdate.ps1"
    cleanup_fixture.write_text(
        "param([switch]$DryRun, [switch]$Apply)\n"
        "if ($DryRun) {\n"
        "  Add-Content -LiteralPath $env:TEAM_SKILLS_TEST_SEQUENCE -Value 'cleanup:dry'\n"
        "  if (Test-Path -LiteralPath $env:TEAM_SKILLS_TEST_LEGACY) { Write-Host 'TEAM_SKILLS_RESULT=DRY_RUN_SAFE' }\n"
        "  else { Write-Host 'TEAM_SKILLS_RESULT=NOT_FOUND' }\n"
        "  exit 0\n"
        "}\n"
        "if ($Apply) {\n"
        "  Add-Content -LiteralPath $env:TEAM_SKILLS_TEST_SEQUENCE -Value 'cleanup:apply'\n"
        "  Remove-Item -LiteralPath $env:TEAM_SKILLS_TEST_LEGACY -Force -ErrorAction SilentlyContinue\n"
        "  Write-Host 'TEAM_SKILLS_RESULT=CLEANED'\n"
        "  exit 0\n"
        "}\n"
        "Write-Host 'TEAM_SKILLS_RESULT=INVALID_INVOCATION'\n"
        "exit 2\n",
        encoding="utf-8-sig",
    )

    installer_fixture = fixtures / "install-team-skills.ps1"
    installer_fixture.write_text(
        "param([string]$ManifestUrl)\n"
        "Add-Content -LiteralPath $env:TEAM_SKILLS_TEST_SEQUENCE -Value 'installer'\n"
        "$manifestPath = Join-Path $env:TEAM_SKILLS_TEST_HOME 'plugins\\team-skills\\.codex-plugin\\plugin.json'\n"
        "New-Item -ItemType Directory -Path (Split-Path $manifestPath -Parent) -Force | Out-Null\n"
        "$payload = [pscustomobject]@{ name='team-skills'; version='0.1.0-test'; release_tag=$env:TEAM_SKILLS_TEST_RELEASE }\n"
        "$payload | ConvertTo-Json | Set-Content -LiteralPath $manifestPath -Encoding UTF8\n"
        "$cache = Join-Path $env:TEAM_SKILLS_TEST_HOME '.codex\\plugins\\cache\\codex-team-skills'\n"
        "Remove-Item -LiteralPath $cache -Recurse -Force -ErrorAction SilentlyContinue\n"
        "Write-Host 'TEAM_SKILLS_RESULT=INSTALLED'\n"
        "Write-Host \"TEAM_SKILLS_RELEASE=$env:TEAM_SKILLS_TEST_RELEASE\"\n"
        "Write-Host 'TEAM_SKILLS_PLUGIN_VERSION=0.1.0-test'\n"
        "exit 0\n",
        encoding="utf-8-sig",
    )

    harness = tmp_path / "run-migrator-harness.ps1"
    harness.write_text(
        definitions
        + "\nfunction Assert-Preflight {\n"
        + "  return [pscustomobject]@{\n"
        + "    Home = $env:TEAM_SKILLS_TEST_HOME\n"
        + "    Plugin = (Join-Path $env:TEAM_SKILLS_TEST_HOME 'plugins\\team-skills')\n"
        + "    Cache = (Join-Path $env:TEAM_SKILLS_TEST_HOME '.codex\\plugins\\cache\\codex-team-skills')\n"
        + "  }\n"
        + "}\n"
        + "function Enter-MigrationMutex($HomePath) {\n"
        + "  $mutex = New-Object -TypeName System.Threading.Mutex\n"
        + "  $mutex.WaitOne() | Out-Null\n"
        + "  return $mutex\n"
        + "}\n"
        + "function Download-File($Url, $Destination) {\n"
        + "  $source = Join-Path $env:TEAM_SKILLS_TEST_FIXTURES (Split-Path $Destination -Leaf)\n"
        + "  Copy-Item -LiteralPath $source -Destination $Destination -Force\n"
        + "}\n"
        + "$outcome = Invoke-Migration\n"
        + "Write-FinalOutcome $outcome\n"
        + "if ($outcome.Result -ne 'MIGRATED_RESTART_REQUIRED' -or $outcome.ExitCode -ne 0) { exit 91 }\n"
        + "$actual = @(Get-Content -LiteralPath $env:TEAM_SKILLS_TEST_SEQUENCE)\n"
        + "$expected = @('cleanup:dry', 'cleanup:apply', 'installer', 'cleanup:dry')\n"
        + "if (($actual -join '|') -ne ($expected -join '|')) { exit 92 }\n"
        + "exit 0\n",
        encoding="utf-8-sig",
    )

    environment = os.environ.copy()
    environment.update(
        {
            "TEAM_SKILLS_TEST_HOME": str(home),
            "TEAM_SKILLS_TEST_FIXTURES": str(fixtures),
            "TEAM_SKILLS_TEST_SEQUENCE": str(sequence),
            "TEAM_SKILLS_TEST_LEGACY": str(legacy_state),
            "TEAM_SKILLS_TEST_RELEASE": release_tag,
        }
    )
    result = subprocess.run(
        [
            executable,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
        env=environment,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "TEAM_SKILLS_MIGRATION_RESULT=MIGRATED_RESTART_REQUIRED" in result.stdout


@pytest.mark.skipif(
    os.name != "nt" or powershell_executable() is None,
    reason="Нужен Windows PowerShell для проверки timeout process tree",
)
def test_windows_child_timeout_stops_descendant_process(tmp_path: Path) -> None:
    executable = powershell_executable()
    assert executable is not None
    source = read(PS1)
    definitions, separator, _ = source.partition("$outcome = Invoke-Migration")
    assert separator
    definitions = definitions.replace(
        "$ChildTimeoutMilliseconds = 600000", "$ChildTimeoutMilliseconds = 5000"
    )

    descendant_pid = tmp_path / "descendant.pid"
    child_fixture = tmp_path / "hanging-child.ps1"
    child_fixture.write_text(
        "$child = Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') "
        "-ArgumentList @('-NoProfile','-NonInteractive','-Command','Start-Sleep -Seconds 60') -PassThru\n"
        "Set-Content -LiteralPath $env:TEAM_SKILLS_TEST_DESCENDANT_PID -Value $child.Id -Encoding ASCII\n"
        "while ($true) { Start-Sleep -Seconds 1 }\n",
        encoding="utf-8-sig",
    )

    harness = tmp_path / "run-timeout-harness.ps1"
    escaped_child = str(child_fixture).replace("'", "''")
    escaped_workdir = str(tmp_path).replace("'", "''")
    harness.write_text(
        definitions
        + "\ntry { Invoke-ChildPowerShell "
        + f"-ScriptPath '{escaped_child}' -Arguments @() -WorkingDirectory '{escaped_workdir}' "
        + "| Out-Null; exit 91 } catch { }\n"
        + "if (-not (Test-Path -LiteralPath $env:TEAM_SKILLS_TEST_DESCENDANT_PID)) { exit 92 }\n"
        + "$descendantId = [int](Get-Content -LiteralPath $env:TEAM_SKILLS_TEST_DESCENDANT_PID -Raw)\n"
        + "Start-Sleep -Milliseconds 300\n"
        + "if (Get-Process -Id $descendantId -ErrorAction SilentlyContinue) { Stop-Process -Id $descendantId -Force -ErrorAction SilentlyContinue; exit 93 }\n"
        + "exit 0\n",
        encoding="utf-8-sig",
    )

    environment = os.environ.copy()
    environment["TEAM_SKILLS_TEST_DESCENDANT_PID"] = str(descendant_pid)
    result = subprocess.run(
        [
            executable,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
        env=environment,
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(
    os.name != "nt" or powershell_executable() is None,
    reason="Нужен Windows PowerShell для проверки лимита вывода",
)
def test_windows_output_flood_is_bounded_and_stops_child(tmp_path: Path) -> None:
    executable = powershell_executable()
    assert executable is not None
    source = read(PS1)
    definitions, separator, _ = source.partition("$outcome = Invoke-Migration")
    assert separator
    definitions = definitions.replace(
        "$ChildTimeoutMilliseconds = 600000", "$ChildTimeoutMilliseconds = 15000"
    ).replace(
        "$ChildOutputMaxCharacters = 1048576", "$ChildOutputMaxCharacters = 4096"
    )

    child_fixture = tmp_path / "flooding-child.ps1"
    child_fixture.write_text(
        "$chunk = 'x' * 16384\n"
        "[Console]::Out.WriteLine($chunk)\n"
        "exit 0\n",
        encoding="utf-8-sig",
    )

    harness = tmp_path / "run-output-flood-harness.ps1"
    escaped_child = str(child_fixture).replace("'", "''")
    escaped_workdir = str(tmp_path).replace("'", "''")
    harness.write_text(
        definitions
        + "\ntry { Invoke-ChildPowerShell "
        + f"-ScriptPath '{escaped_child}' -Arguments @() -WorkingDirectory '{escaped_workdir}' "
        + "| Out-Null; exit 91 } catch {\n"
        + "  if ($_.Exception.Message -notmatch 'лимит вывода') { Write-Error $_; exit 92 }\n"
        + "}\nexit 0\n",
        encoding="utf-8-sig",
    )

    result = subprocess.run(
        [
            executable,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
