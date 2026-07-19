from __future__ import annotations

from pathlib import Path

import yaml

from conftest import ROOT


INSTALLER_DIR = ROOT / "installer"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def test_one_shot_source_entrypoints_exist() -> None:
    expected = {
        "install-team-skills.cmd",
        "install-team-skills.ps1",
        "install-team-skills.command",
        "migrate-team-skills.cmd",
        "migrate-team-skills.ps1",
        "migrate-team-skills.command",
        "uninstall-team-skills.ps1",
        "uninstall-team-skills.command",
        "remove-team-skills-autoupdate.ps1",
        "remove-team-skills-autoupdate.command",
        "team-skills-registry.py",
    }
    assert expected.issubset({path.name for path in INSTALLER_DIR.iterdir() if path.is_file()})

    for obsolete in (
        "bootstrap-team-skills.ps1",
        "bootstrap-team-skills.sh",
        "update-team-skills.ps1",
        "update-team-skills.sh",
        "team-skills-status.ps1",
        "team-skills-status.command",
        "refresh-team-skills.command",
        "team-skills-public-key.pem",
    ):
        assert not (INSTALLER_DIR / obsolete).exists()


def test_windows_installer_is_temp_only_and_has_no_legacy_cleanup() -> None:
    install = read(INSTALLER_DIR / "install-team-skills.ps1")
    for required in (
        "__TEAM_SKILLS_RELEASE_TAG__",
        "manifest.json",
        "team-skills-bundle.zip",
        "Get-FileHash -Algorithm SHA256",
        ".codex-plugin\\plugin.json",
        "Invalidate-CodexPluginCache",
        "Replace-Plugin",
        "ValidateOnly",
        "Автообновления нет",
        "TEAM_SKILLS_RESULT=INSTALLED",
        "TEAM_SKILLS_RELEASE=",
    ):
        assert required in install

    for forbidden in (
        "releases/latest/download/manifest.json",
        "latest.json",
        "Verify-Signature",
        "PinnedPublicKey",
        "Register-ScheduledTask",
        "Unregister-ScheduledTask",
        "New-ScheduledTaskTrigger",
        "CodexTeamSkills",
        "bootstrap-team-skills",
        "update-team-skills",
        "state.json",
        "last-repair.json",
        "team-skills-registry.py",
        "pull-skills.sh",
    ):
        assert forbidden not in install


def test_windows_atomic_replace_uses_a_real_temporary_backup_path() -> None:
    install = read(INSTALLER_DIR / "install-team-skills.ps1")

    atomic_write = install[
        install.index("function Write-Utf8NoBomAtomic") : install.index("function Save-OptionalFile")
    ]
    assert '$backup = "$fullPath.bak.$transactionId"' in atomic_write
    assert "[System.IO.File]::Replace($temporary, $fullPath, $backup)" in atomic_write
    assert "[System.IO.File]::Replace($temporary, $fullPath, $null)" not in atomic_write
    assert atomic_write.count("Remove-Item -LiteralPath $backup") == 2


def test_macos_installer_is_temp_only_and_has_no_legacy_cleanup() -> None:
    install = read(INSTALLER_DIR / "install-team-skills.command")
    for required in (
        "__TEAM_SKILLS_RELEASE_TAG__",
        "manifest.json",
        "team-skills-bundle.zip",
        "sha256",
        ".codex-plugin/plugin.json",
        ".codex/plugins/cache/$MARKETPLACE_NAME",
        "--validate-only",
        "sys.version_info >= (3, 11)",
        "Автообновления нет",
        "TEAM_SKILLS_RESULT=INSTALLED",
        "TEAM_SKILLS_RELEASE=",
    ):
        assert required in install

    for forbidden in (
        "releases/latest/download/manifest.json",
        "latest.json",
        "verify_signature",
        "EXPECTED_PUBLIC_KEY_SHA256",
        "launchctl",
        "CodexTeamSkills",
        "bootstrap-team-skills",
        "update-team-skills",
        "state.json",
        "team-skills-registry.py",
        "pull-skills.sh",
    ):
        assert forbidden not in install


def test_uninstall_is_separate_from_legacy_cleanup() -> None:
    windows = read(INSTALLER_DIR / "uninstall-team-skills.ps1")
    macos = read(INSTALLER_DIR / "uninstall-team-skills.command")

    assert "remove-team-skills-autoupdate.ps1 -DryRun" in windows
    assert "Unregister-ScheduledTask" not in windows
    assert "team-skills-registry.py" not in windows
    assert "remove-team-skills-autoupdate.command --dry-run" in macos
    assert "launchctl bootout" not in macos
    assert "team-skills-registry.py" not in macos

    for content in (windows, macos):
        assert "marketplace.json" in content
        assert "codex-team-skills managed block" in content


def test_migration_is_a_one_shot_release_bound_orchestrator() -> None:
    windows = read(INSTALLER_DIR / "migrate-team-skills.ps1")
    macos = read(INSTALLER_DIR / "migrate-team-skills.command")

    for content in (windows, macos):
        assert "__TEAM_SKILLS_RELEASE_TAG__" in content
        assert "remove-team-skills-autoupdate" in content
        assert "install-team-skills" in content
        assert "MIGRATED_RESTART_REQUIRED" in content
        assert "INSTALLER_REGRESSION_CLEANED" in content
        assert "releases/latest" not in content
        assert "Register-ScheduledTask" not in content
        assert "LaunchAgents" not in content
        assert "state.json" not in content


def test_install_and_migrate_paths_cannot_register_background_persistence() -> None:
    windows = "\n".join(
        read(INSTALLER_DIR / name).lower()
        for name in (
            "install-team-skills.cmd",
            "install-team-skills.ps1",
            "migrate-team-skills.cmd",
            "migrate-team-skills.ps1",
        )
    )
    macos = "\n".join(
        read(INSTALLER_DIR / name).lower()
        for name in ("install-team-skills.command", "migrate-team-skills.command")
    )

    for primitive in (
        "register-scheduledtask",
        "new-scheduledtask",
        "schtasks",
        "schedule.service",
        "currentversion\\run",
        "new-service",
        "sc.exe create",
    ):
        assert primitive not in windows

    for primitive in (
        "launchctl",
        "/library/launchagents",
        "runatload",
        "keepalive",
        "crontab",
    ):
        assert primitive not in macos


def test_user_docs_keep_codex_and_claude_delivery_separate() -> None:
    colleague = read(ROOT / "START_HERE_CONNECT_CODEX_SKILLS.md")
    admin = read(ROOT / "admin-onboarding-guide.md")
    assert "migrate-team-skills.cmd" in colleague
    assert "migrate-team-skills.command" in colleague
    assert "remove-team-skills-autoupdate.ps1" in admin
    assert "remove-team-skills-autoupdate.command" in admin
    assert "нативный marketplace" in colleague
    assert "pull-skills.sh" not in colleague


def test_ci_builds_and_validates_manual_only_release() -> None:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    assert "python -m pytest" in str(jobs["pytest"]["steps"])
    assert "scripts/build_release_bundle.py" in str(jobs["build-release-bundle"]["steps"])
    assert jobs["windows-powershell-smoke"]["runs-on"] == "windows-latest"
    assert jobs["macos-one-shot-smoke"]["runs-on"] == "macos-latest"
    assert jobs["publish"]["needs"] == ["windows-powershell-smoke", "macos-one-shot-smoke"]

    build_script = read(ROOT / "scripts" / "build_release_bundle.py")
    for marker in ("team-skills-bundle.zip", "manifest.json", "sha256", "release_tag"):
        assert marker in build_script
    assert "support_files" not in build_script
    assert "BUNDLE_FORBIDDEN_FILE_NAMES" in build_script
    for forbidden_name in ("latest.json", "team-skills-public-key.pem"):
        assert f'"{forbidden_name}"' in build_script

    workflow_text = str(workflow)
    assert "gh release create" in workflow_text
    assert "TEAM_SKILLS_SIGNING_KEY_PEM" not in workflow_text
    assert "manifest.json.sig" not in workflow_text
    assert "Installer changed the Scheduled Task set" in workflow_text
    assert "launch_agents_before" in workflow_text
