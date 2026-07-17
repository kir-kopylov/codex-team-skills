from __future__ import annotations

from conftest import ROOT


INSTALLER = ROOT / "installer"
WINDOWS_INTEGRATION = ROOT / "tests" / "windows" / "windows-update-repair-integration.ps1"


def read(name: str) -> str:
    return (INSTALLER / name).read_text(encoding="utf-8")


def test_updater_exposes_stable_failure_and_repair_state_contracts() -> None:
    update = read("update-team-skills.ps1")
    for marker in (
        "SIGNATURE_SETUP_FAILED",
        "SIGNATURE_INVALID",
        "DOWNLOAD_FAILED",
        "CHECKSUM_MISMATCH",
        "PLUGIN_MISSING",
        "INSTALL_FAILED",
        "SCHEDULE_FAILED",
        "UNKNOWN_FAILURE",
        "schema_version = 1",
        "failed_at",
        "operation = $Script:CurrentOperation",
        "completed_at",
        "support_files_refreshed = $true",
        "registry_repaired = $true",
        "cache_invalidated = $true",
        "scheduled_task_present = $true",
        "plugin_changed = $false",
    ):
        assert marker in update

    repair_block = update.split("function Repair-Install", 1)[1].split("if ($VerifySignatureOnly)", 1)[0]
    assert "Write-RepairState" in repair_block
    assert "Write-State" not in repair_block
    assert "Swap" not in repair_block


def test_updater_retry_policy_is_bounded_and_has_no_fallbacks() -> None:
    update = read("update-team-skills.ps1")
    for marker in (
        "CODEX_TEAM_SKILLS_DOWNLOAD_TIMEOUT_SEC",
        "CODEX_TEAM_SKILLS_DOWNLOAD_MAX_ATTEMPTS",
        "45 1 300",
        "3 1 5",
        "-TimeoutSec $Script:DownloadTimeoutSec",
        "Invoke-Download $Url $Destination 3",
        "Invoke-Download $entry.url $dest 2",
        "$attempt -eq 1) { 2 } else { 5 }",
        '"Timeout", "ConnectFailure", "ConnectionClosed"',
        "$statusCode -eq 408",
        "$statusCode -eq 429",
        "$statusCode -ge 500",
    ):
        assert marker in update

    assert "-Method Head" not in update
    assert "curl.exe" not in update
    assert "git clone" not in update.lower()


def test_repair_refreshes_support_and_schedule_without_plugin_swap() -> None:
    update = read("update-team-skills.ps1")
    repair_block = update.split("function Repair-Install", 1)[1].split("if ($VerifySignatureOnly)", 1)[0]
    for marker in (
        "Test-SignatureSetup",
        "Get-ReleaseManifest",
        "Download-SupportFiles",
        "Install-SupportFiles",
        "Invoke-RegistryRepair",
        "Invoke-CacheInvalidation",
        "Invoke-ScheduleRegistration",
        "Write-RepairState",
        "Clear-FailureState",
    ):
        assert marker in repair_block
    assert "Start-PluginSwap" not in repair_block
    assert '"update-team-skills.ps1"' in update
    assert '"$dest.next"' in update


def test_full_update_invalidates_cache_after_plugin_swap_before_success_state() -> None:
    update = read("update-team-skills.ps1")
    full_update = update.rsplit("if ($RepairInstall)", 1)[1]
    assert full_update.index("Start-PluginSwap $pluginRoot") < full_update.index("Invoke-CacheInvalidation")
    assert full_update.index("Invoke-CacheInvalidation") < full_update.index("Write-State $manifest")
    assert "Undo-PluginSwap" in full_update


def test_status_separates_task_success_repair_and_failure() -> None:
    status = read("team-skills-status.ps1")
    assert "Не удалось прочитать ${Path}:" in status
    assert "Не удалось прочитать $Path:" not in status
    for marker in (
        "Автообновление: включено",
        "Автообновление: отсутствует",
        "Автообновление: не удалось проверить",
        "State:",
        "LastRunTime:",
        "LastTaskResult:",
        "NextRunTime:",
        "Последнее успешное полное обновление:",
        "Последний успешный repair:",
        "Активная ошибка update/repair:",
        "requires Codex restart; cannot be proven from shell",
    ):
        assert marker in status


def test_bootstrap_owns_idempotent_schedule_registration() -> None:
    bootstrap = read("bootstrap-team-skills.ps1")
    install = read("install-team-skills.ps1")
    assert "[switch]$RegisterAutoUpdate" in bootstrap
    assert "Register-ScheduledTask" in bootstrap
    assert "-Force | Out-Null" in bootstrap
    assert "-DaysInterval 2" in bootstrap
    assert "-File `\"$PSCommandPath`\"" in bootstrap
    assert "& powershell.exe" in install
    assert "Invoke-BootstrapProcess -RegisterAutoUpdate" in install
    assert install.index("if ($updateExitCode -ne 0)") < install.index("Invoke-BootstrapProcess -RegisterAutoUpdate")


def test_windows_repair_fixture_starts_from_an_existing_updater() -> None:
    integration = WINDOWS_INTEGRATION.read_text(encoding="utf-8")
    current_updater = 'Copy-Item $Updater (Join-Path $BinDir "update-team-skills.ps1") -Force'
    assert current_updater in integration
    assert integration.index(current_updater) < integration.index('$repair = Invoke-WindowsPowerShell $Updater @("-RepairInstall")')
    assert 'Test-Path (Join-Path $BinDir "update-team-skills.ps1.next")' in integration
    assert "Get-Content $MarketplacePath -Raw | ConvertFrom-Json" in integration
    assert '$_.name -eq "team-skills"' in integration
