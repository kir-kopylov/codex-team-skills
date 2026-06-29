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
        "bootstrap-team-skills.ps1",
        "bootstrap-team-skills.sh",
        "update-team-skills.ps1",
        "update-team-skills.sh",
        "uninstall-team-skills.ps1",
        "uninstall-team-skills.command",
        "team-skills-status.ps1",
        "team-skills-status.command",
        "team-skills-registry.py",
        "team-skills-public-key.pem",
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
    assert "latest.json" in update
    assert "team-skills-bundle.zip" in update
    assert "Get-FileHash -Algorithm SHA256" in update
    assert ".codex-plugin\\plugin.json" in update
    assert "previous" in update
    assert "Verify-Signature" in update
    assert "runtime_version" in update
    assert "codex-team-skills" in update
    assert ".codex\\plugins\\cache\\codex-team-skills" in update
    assert "Invalidate-CodexPluginCache" in update

    assert "Unregister-ScheduledTask" in uninstall
    assert "marketplace.json" in uninstall
    assert "codex-team-skills managed block" in uninstall


def test_macos_installer_uses_release_bundle_and_launchagent() -> None:
    install = read(INSTALLER_DIR / "install-team-skills.command")
    update = read(INSTALLER_DIR / "update-team-skills.sh")
    uninstall = read(INSTALLER_DIR / "uninstall-team-skills.command")

    assert "releases/latest/download" in install
    assert "com.codex-team-skills.autoupdate" in install
    assert "<integer>172800</integer>" in install
    assert "launchctl load" in install
    assert "bootstrap-team-skills.sh" in install

    assert "manifest.json" in update
    assert "latest.json" in update
    assert "team-skills-bundle.zip" in update
    assert "hashlib.sha256" in update
    assert ".codex-plugin/plugin.json" in update
    assert "previous" in update
    assert "verify_signature" in update
    assert "runtime_version" in update
    assert "team-skills-registry.py" in update
    assert ".codex/plugins/cache/$MARKETPLACE_NAME" in update
    assert "invalidate_codex_plugin_cache" in update

    assert "launchctl unload" in uninstall
    assert "marketplace.json" in uninstall
    assert "Codex registry" in uninstall


def test_user_docs_do_not_require_github_desktop() -> None:
    colleague = read(ROOT / "START_HERE_CONNECT_CODEX_SKILLS.md")
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
    pytest_job = workflow["jobs"]["pytest"]
    pytest_step_text = "\n".join(str(step) for step in pytest_job["steps"])
    bundle_job = workflow["jobs"]["build-release-bundle"]
    bundle_step_text = "\n".join(str(step) for step in bundle_job["steps"])

    assert "python -m pytest" in pytest_step_text
    assert "scripts/build_release_bundle.py" in bundle_step_text
    assert "actions/upload-artifact" in bundle_step_text
    assert bundle_job["if"] == "needs.release-scope.outputs.run_release_checks == 'true'"
    assert bundle_job["needs"] == [
        "pr-governance",
        "installer-release-gate",
        "release-scope",
        "pytest",
        "claude-sync-smoke",
    ]

    build_script = (ROOT / "scripts" / "build_release_bundle.py").read_text(encoding="utf-8")
    assert "team-skills-bundle.zip" in build_script
    assert "manifest.json" in build_script
    assert "latest.json" in build_script
    assert "sha256" in build_script
    assert "runtime_version" in build_script
    assert "release_id" in build_script
    assert "team-skills-v" in build_script

    workflow_text = "\n".join(str(job) for job in workflow["jobs"].values())
    assert "manifest.json.sig" in workflow_text
    assert "latest.json.sig" in workflow_text
    assert "windows-powershell-smoke" in workflow["jobs"]
    assert "gh release create" in workflow_text
    assert "gh release delete team-skills-latest" not in workflow_text
