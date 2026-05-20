from __future__ import annotations

from pathlib import Path

import yaml

from conftest import ROOT


INSTALLER_DIR = ROOT / "installer"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_installer_files_exist() -> None:
    expected = [
        "install-team-skills.cmd",
        "install-team-skills.ps1",
        "install-team-skills.command",
        "update-team-skills.ps1",
        "update-team-skills.sh",
        "uninstall-team-skills.ps1",
        "uninstall-team-skills.command",
        "team-skills-status.ps1",
        "team-skills-status.command",
    ]
    for name in expected:
        path = INSTALLER_DIR / name
        assert path.exists(), f"installer file missing: {path}"
        assert path.stat().st_size > 0, f"installer file is empty: {path}"


def test_windows_installer_uses_release_bundle_and_task_scheduler() -> None:
    install = read(INSTALLER_DIR / "install-team-skills.ps1")
    update = read(INSTALLER_DIR / "update-team-skills.ps1")
    uninstall = read(INSTALLER_DIR / "uninstall-team-skills.ps1")

    assert "releases/latest/download" in install
    assert "Register-ScheduledTask" in install
    assert "New-ScheduledTaskTrigger -Daily -DaysInterval 2" in install
    assert "Codex Team Skills Auto Update" in install

    assert "manifest.json" in update
    assert "team-skills-bundle.zip" in update
    assert "Get-FileHash -Algorithm SHA256" in update
    assert ".codex-plugin\\plugin.json" in update
    assert "previous" in update

    assert "Unregister-ScheduledTask" in uninstall
    assert "marketplace.json" in uninstall


def test_macos_installer_uses_release_bundle_and_launchagent() -> None:
    install = read(INSTALLER_DIR / "install-team-skills.command")
    update = read(INSTALLER_DIR / "update-team-skills.sh")
    uninstall = read(INSTALLER_DIR / "uninstall-team-skills.command")

    assert "releases/latest/download" in install
    assert "com.codex-team-skills.autoupdate" in install
    assert "<integer>172800</integer>" in install
    assert "launchctl load" in install

    assert "manifest.json" in update
    assert "team-skills-bundle.zip" in update
    assert "shasum -a 256" in update
    assert ".codex-plugin/plugin.json" in update
    assert "previous" in update

    assert "launchctl unload" in uninstall
    assert "marketplace.json" in uninstall


def test_user_docs_do_not_require_github_desktop() -> None:
    colleague = read(ROOT / "SEND_TO_COLLEAGUE.md")
    admin = read(ROOT / "admin-onboarding-guide.md")

    assert "GitHub Desktop" not in colleague
    assert "GitHub Desktop" not in admin
    assert "clone repo" not in colleague
    assert "install-team-skills.ps1" in colleague
    assert "install-team-skills.command" in colleague
    assert "User mode" in admin
    assert "Author mode" in admin


def test_ci_builds_validated_release_bundle() -> None:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8"))
    job = workflow["jobs"]["pytest"]
    step_text = "\n".join(str(step) for step in job["steps"])

    assert "python -m pytest" in step_text
    assert "team-skills-bundle.zip" in step_text
    assert "manifest.json" in step_text
    assert "sha256" in step_text
    assert "actions/upload-artifact" in step_text
    assert "gh release create team-skills-latest" in step_text
