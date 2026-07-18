"""Регрессии для минимальной one-shot доставки без собственного updater runtime."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import ROOT


INSTALLER_DIR = ROOT / "installer"
SHELL_SCRIPTS = sorted(
    [
        *INSTALLER_DIR.glob("*.sh"),
        *INSTALLER_DIR.glob("*.command"),
        *(ROOT / "scripts").glob("*.sh"),
    ]
)


@pytest.mark.skipif(shutil.which("zsh") is None, reason="нужен zsh для syntax-smoke macOS scripts")
@pytest.mark.parametrize("script", SHELL_SCRIPTS, ids=lambda path: path.name)
def test_shell_scripts_pass_zsh_syntax_check(script: Path) -> None:
    result = subprocess.run(["zsh", "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, f"{script.name} не прошёл zsh -n:\n{result.stderr}"


def test_shell_script_set_contains_one_shot_entrypoints() -> None:
    names = {path.name for path in SHELL_SCRIPTS}
    assert {
        "install-team-skills.command",
        "migrate-team-skills.command",
        "uninstall-team-skills.command",
        "remove-team-skills-autoupdate.command",
        "pull-skills.sh",
    }.issubset(names)


def test_client_signing_runtime_is_absent() -> None:
    assert not (INSTALLER_DIR / "team-skills-public-key.pem").exists()
    assert not (ROOT / "tests" / "fixtures" / "windows-signature").exists()

    combined = "\n".join(
        path.read_text(encoding="utf-8-sig")
        for path in INSTALLER_DIR.iterdir()
        if path.is_file() and path.suffix in {".ps1", ".command", ".cmd", ".py"}
    )
    for forbidden in (
        "TEAM_SKILLS_SIGNING_KEY_PEM",
        "Verify-Signature",
        "verify_signature",
        "manifest.json.sig",
        "latest.json.sig",
        "PinnedPublicKey",
        "EXPECTED_PUBLIC_KEY_SHA256",
    ):
        assert forbidden not in combined


def test_docs_state_the_actual_github_https_trust_boundary() -> None:
    guide = (ROOT / "admin-onboarding-guide.md").read_text(encoding="utf-8")
    assert "GitHub Releases и HTTPS" in guide
    assert "SHA-256 обнаруживает повреждение" in guide
    assert "не является независимой подписью" in guide
