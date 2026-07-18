from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import ROOT


SCRIPT = ROOT / "installer" / "remove-team-skills-autoupdate.ps1"

OFFICIAL_LEGACY_SUPPORT_NAMES = {
    "install-team-skills.cmd",
    "install-team-skills.ps1",
    "install-team-skills.command",
    "bootstrap-team-skills.ps1",
    "bootstrap-team-skills.sh",
    "update-team-skills.ps1",
    "update-team-skills.sh",
    "uninstall-team-skills.ps1",
    "uninstall-team-skills.command",
    "team-skills-status.ps1",
    "team-skills-status.command",
    "refresh-team-skills.command",
    "pull-skills.sh",
    "team-skills-registry.py",
    "team-skills-public-key.pem",
}


def script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8-sig")


def powershell_string_array(text: str, variable: str) -> set[str]:
    match = re.search(rf"\${re.escape(variable)}\s*=\s*@\((.*?)\n\)", text, re.DOTALL)
    assert match is not None
    return set(re.findall(r'^\s*"([^"]+)"\s*,?\s*$', match.group(1), re.MULTILINE))


def _powershell_executable() -> str | None:
    return shutil.which("powershell.exe") or shutil.which("pwsh")


def test_windows_cleanup_exposes_only_dry_run_and_apply() -> None:
    text = script_text()

    assert "[switch]$DryRun" in text
    assert "[switch]$Apply" in text
    assert "-DryRun | -Apply" in text
    assert "exit 2" in text
    assert "InstallRoot" not in text.split("param(", 1)[1].split(")", 1)[0]
    assert "CODEX_TEAM_SKILLS_HOME" not in text


def test_windows_cleanup_requires_exact_scheduler_attribution() -> None:
    text = script_text()

    assert '$TaskName = "Codex Team Skills Auto Update"' in text
    assert '$TaskPath = "\\"' in text
    assert "actions.Count -ne 1" in text
    assert 'powershell.exe"' in text
    assert "-NoProfile\\s+-ExecutionPolicy\\s+Bypass\\s+-File" in text
    assert "Get-TaskScriptPath" in text
    assert "Get-NormalizedPath (Split-Path $binPath -Parent)" in text
    assert "team-skills-auto-update-with-git-fallback.ps1" in text


def test_windows_cleanup_fails_closed_on_unsafe_tree() -> None:
    text = script_text()

    assert "ReparsePoint" in text
    assert "AllowedRootEntries" in text
    assert "AllowedBinEntries" in text
    assert "неизвестный объект" in text
    assert "*.backup.*" in text
    assert "*.previous.*" in text
    assert "*.stale.*" in text
    assert 'GetFileName($fullRoot) -cne "CodexTeamSkills"' in text
    assert "вне домашней директории" in text
    assert 'Source = "canonical-fallback"' in text


def test_windows_cleanup_accepts_full_official_legacy_bin_allowlist() -> None:
    text = script_text()

    assert OFFICIAL_LEGACY_SUPPORT_NAMES <= powershell_string_array(text, "AllowedBinEntries")


def test_windows_cleanup_only_accepts_exact_registry_bytecode_in_pycache() -> None:
    text = script_text()

    assert '$AllowedBinDirectory = "__pycache__"' in text
    assert "$AllowedRegistryBytecodePattern = '^team-skills-registry\\.cpython-\\d+\\.pyc$'" in text
    assert "$entry.Name -cne $AllowedBinDirectory" in text
    assert "$entry -is [System.IO.DirectoryInfo]" in text
    assert "$bytecode.PSIsContainer" in text
    assert "$bytecode -is [System.IO.FileInfo]" in text
    assert "(Test-ReparsePoint $bytecode)" in text
    assert "$bytecode.Name -cnotmatch $AllowedRegistryBytecodePattern" in text
    assert "В __pycache__ обнаружен неизвестный объект" in text


def _create_official_legacy_root(home: Path, *, pycache_name: str) -> Path:
    root = home / "AppData" / "Local" / "CodexTeamSkills"
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True)
    for name in OFFICIAL_LEGACY_SUPPORT_NAMES:
        (bin_dir / name).write_text("legacy support\n", encoding="utf-8")
    pycache = bin_dir / "__pycache__"
    pycache.mkdir()
    (pycache / pycache_name).write_bytes(b"legacy bytecode")
    return root


def _run_windows_cleanup_fixture(home: Path) -> subprocess.CompletedProcess[str]:
    executable = _powershell_executable()
    assert executable is not None
    literal_path = str(SCRIPT).replace("'", "''")
    command = (
        "Set-Variable -Name HOME -Value $env:TEAM_SKILLS_TEST_HOME -Scope Global -Force; "
        "function Get-ScheduledTask { [CmdletBinding()] param() return @() }; "
        "function Get-CimInstance { [CmdletBinding()] param([string]$ClassName) return @() }; "
        f"& '{literal_path}' -DryRun"
    )
    environment = os.environ.copy()
    environment["HOME"] = str(home)
    environment["USERPROFILE"] = str(home)
    environment["TEAM_SKILLS_TEST_HOME"] = str(home)
    environment["LOCALAPPDATA"] = str(home / "AppData" / "Local")
    for name in (
        "CODEX_TEAM_SKILLS_PLUGIN_DIR",
        "CODEX_TEAM_SKILLS_MARKETPLACE",
        "CODEX_TEAM_SKILLS_MARKETPLACE_ROOT",
        "CODEX_TEAM_SKILLS_CODEX_CONFIG",
        "CODEX_TEAM_SKILLS_CODEX_PLUGIN_CACHE_DIR",
    ):
        environment.pop(name, None)
    return subprocess.run(
        [executable, "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
        env=environment,
    )


@pytest.mark.skipif(
    os.name != "nt" or _powershell_executable() is None,
    reason="Нужен Windows с PowerShell",
)
def test_full_official_legacy_bin_with_exact_pycache_is_accepted(tmp_path: Path) -> None:
    home = tmp_path / "home"
    root = _create_official_legacy_root(
        home,
        pycache_name="team-skills-registry.cpython-311.pyc",
    )

    result = _run_windows_cleanup_fixture(home)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Результат: DRY_RUN_SAFE" in result.stdout
    assert root.is_dir()


@pytest.mark.skipif(
    os.name != "nt" or _powershell_executable() is None,
    reason="Нужен Windows с PowerShell",
)
def test_unexpected_pycache_content_is_refused_without_mutation(tmp_path: Path) -> None:
    home = tmp_path / "home"
    root = _create_official_legacy_root(home, pycache_name="unrelated.cpython-311.pyc")

    result = _run_windows_cleanup_fixture(home)

    assert result.returncode == 3, result.stdout + result.stderr
    assert "Результат: REFUSED_UNSAFE" in result.stdout
    assert "В __pycache__ обнаружен неизвестный объект" in result.stdout
    assert root.is_dir()


def test_windows_cleanup_measures_protected_artifacts_and_exact_processes() -> None:
    text = script_text()

    for expected in (
        "Plugin hash",
        "Marketplace hash",
        "Config hash",
        "Active cache hash",
        "Get-FileHash -LiteralPath",
        "Get-TextSha256",
        "Get-CimInstance Win32_Process",
        "Get-FileArgumentFromCommandLine",
        "Wait-ForExactUpdaterProcesses $discovery.Root 10",
        "Stop-Process -Id $candidate.Id -Force",
    ):
        assert expected in text


def test_protected_overrides_are_additive_to_default_paths() -> None:
    text = script_text()

    for category in ("Plugin", "Marketplace", "Config", "Cache"):
        assert f"${category}Paths = @($Default{category}Path)" in text
        assert f"Get-ProtectedSetFingerprint ${category}Paths" in text
    assert "$PluginPaths += $env:CODEX_TEAM_SKILLS_PLUGIN_DIR" in text
    assert "$MarketplacePaths += $env:CODEX_TEAM_SKILLS_MARKETPLACE" in text
    assert "$ConfigPaths += $env:CODEX_TEAM_SKILLS_CODEX_CONFIG" in text
    assert "$CachePaths += $env:CODEX_TEAM_SKILLS_CODEX_PLUGIN_CACHE_DIR" in text
    assert "@($PluginPaths) + @($MarketplacePaths) + @($ConfigPaths) + @($CachePaths)" in text


def test_windows_dry_run_exits_before_every_mutation() -> None:
    text = script_text()
    dry_run_gate = text.index("if ($DryRun)")

    for mutation in (
        "Disable-ScheduledTask",
        "Stop-ScheduledTask",
        "Stop-Process",
        "Unregister-ScheduledTask",
        "Remove-Item -LiteralPath $discovery.Root",
    ):
        assert text.index(mutation) > dry_run_gate
    assert text.count("Remove-Item -LiteralPath $discovery.Root") == 1


def test_apply_revalidates_identity_and_refreshes_task_state_before_stop() -> None:
    text = script_text()
    dry_run_gate = text.index("if ($DryRun)")
    rediscovery = text.index("$confirmedDiscovery = Get-Discovery", dry_run_gate)
    disable = text.index("Disable-ScheduledTask", rediscovery)
    refreshed_state = text.index("$tasksAfterDisable = @(Get-TargetTasks)", disable)
    stop = text.index("Stop-ScheduledTask", refreshed_state)

    assert rediscovery < disable < refreshed_state < stop
    assert "$confirmedDiscovery.Source -cne $discovery.Source" in text
    assert "Test-SamePath $confirmedDiscovery.Root $discovery.Root" in text
    assert "Test-SamePath $confirmedDiscovery.ActionScript $discovery.ActionScript" in text
    assert '[string]$tasksAfterDisable[0].State -eq "Running"' in text


def test_windows_cleanup_has_contract_outcomes_and_exit_codes() -> None:
    text = script_text()

    for outcome in ("DRY_RUN_SAFE", "CLEANED", "NOT_FOUND", "REFUSED_UNSAFE", "INCOMPLETE"):
        assert outcome in text
    for exit_code in ("exit 0", "exit 2", "exit 3", "exit 4"):
        assert exit_code in text
    assert 'Write-Host "[team-skills] Результат: $Outcome"' in text


@pytest.mark.skipif(_powershell_executable() is None, reason="PowerShell недоступен")
def test_windows_cleanup_parses_in_available_powershell() -> None:
    executable = _powershell_executable()
    assert executable is not None
    literal_path = str(SCRIPT).replace("'", "''")
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
