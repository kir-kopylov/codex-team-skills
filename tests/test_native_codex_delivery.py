from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ROOT
from scripts.smoke_native_codex_marketplace import assert_git_marketplace_source


INSTALL = "codex plugin marketplace add kir-kopylov/codex-team-skills --ref main --json"
ADD_PLUGIN = "codex plugin add team-skills@codex-team-skills --json"
UPDATE = "codex plugin marketplace upgrade codex-team-skills --json"
REMOVE_PLUGIN = "codex plugin remove team-skills@codex-team-skills --json"
REMOVE_MARKETPLACE = "codex plugin marketplace remove codex-team-skills --json"

PUBLIC_DELIVERY_FILES = [
    ROOT / "README.md",
    ROOT / "catalog.md",
    ROOT / "quickstart.md",
    ROOT / "START_HERE_CONNECT_CODEX_SKILLS.md",
    ROOT / "START_HERE_RECONNECT_CODEX_SKILLS.md",
    ROOT / "admin-onboarding-guide.md",
    ROOT / "docs/platform-overview.md",
    ROOT / "CLAUDE.md",
    ROOT / "AGENTS.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / ".github/workflows/tests.yml",
]

FORBIDDEN_DELIVERY_MARKERS = (
    "releases/latest/download",
    "migrate-team-skills.cmd",
    "migrate-team-skills.command",
    "install-team-skills.cmd",
    "ExecutionPolicy Bypass",
    "build_release_bundle.py",
    "team-skills-bundle.zip",
    "одноразовым установщиком",
)

FORBIDDEN_SHIPPED_SKILL_DELIVERY_MARKERS = (
    "releases/latest/download",
    "migrate-team-skills.cmd",
    "migrate-team-skills.command",
    "install-team-skills.cmd",
    "install-team-skills.command",
    "install-team-skills.ps1",
    "team-skills-bundle.zip",
    "signed one-shot Windows installer",
    "подписанный one-shot installer",
    "повторным ручным запуском подписанного installer",
)


def test_custom_codex_delivery_is_absent() -> None:
    assert not (ROOT / "installer").exists()
    assert not (ROOT / "scripts/build_release_bundle.py").exists()
    assert not (ROOT / "scripts/install_plugin.sh").exists()


def test_public_delivery_docs_do_not_restore_download_and_execute() -> None:
    for path in PUBLIC_DELIVERY_FILES:
        text = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN_DELIVERY_MARKERS:
            assert marker not in text, f"{path} вернул запрещённую схему доставки: {marker}"


def test_shipped_skills_do_not_restore_retired_team_skills_delivery() -> None:
    skills_root = ROOT / "plugins/team-skills/skills"
    text_suffixes = {".md", ".yaml", ".yml", ".json", ".toml", ".txt"}
    for path in skills_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in text_suffixes:
            continue
        text = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN_SHIPPED_SKILL_DELIVERY_MARKERS:
            assert marker not in text, f"{path} вернул старую Team Skills delivery: {marker}"


def test_clean_install_update_and_remove_commands_are_documented() -> None:
    connect = (ROOT / "START_HERE_CONNECT_CODEX_SKILLS.md").read_text(encoding="utf-8")
    quickstart = (ROOT / "quickstart.md").read_text(encoding="utf-8")
    for command in (INSTALL, ADD_PLUGIN, UPDATE, REMOVE_PLUGIN, REMOVE_MARKETPLACE):
        assert command in connect
        assert command in quickstart
    assert "codex plugin --help" in connect
    assert "0.144.4" in connect


def test_legacy_transition_is_evidence_gated() -> None:
    guide = (ROOT / "START_HERE_RECONNECT_CODEX_SKILLS.md").read_text(encoding="utf-8")
    required_markers = (
        "# BEGIN codex-team-skills managed block",
        "~/.codex/config.toml",
        "~/plugins/team-skills",
        "~/.codex/plugins/cache/codex-team-skills",
        "Codex Team Skills Auto Update",
        "%LOCALAPPDATA%\\CodexTeamSkills",
        "com.codex-team-skills.autoupdate",
        "~/Library/Application Support/CodexTeamSkills",
        "UTF-8 без BOM",
        "остановись без удаления",
    )
    for marker in required_markers:
        assert marker in guide


def test_ci_runs_native_marketplace_smoke_on_windows_and_macos() -> None:
    workflow = (ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8")
    assert "windows-latest" in workflow
    assert "macos-latest" in workflow
    assert "@openai/codex@0.144.4" in workflow
    assert "scripts/smoke_native_codex_marketplace.py" in workflow
    assert "github.event.pull_request.head.repo.full_name || github.repository" in workflow
    assert "gh release create" not in workflow


def test_smoke_reconfigures_cp1252_output_to_utf8() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import scripts.smoke_native_codex_marketplace as smoke; "
                "smoke.configure_utf8_output(); print('русский вывод')"
            ),
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
        check=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.stdout == "русский вывод\n"


def test_remote_smoke_requires_the_requested_git_marketplace_source() -> None:
    installed = {
        "marketplaceSource": {
            "sourceType": "git",
            "source": "https://github.com/kir-kopylov/codex-team-skills.git",
        }
    }
    assert_git_marketplace_source(installed, "kir-kopylov/codex-team-skills")

    local = {"marketplaceSource": {"sourceType": "local", "source": str(ROOT)}}
    with pytest.raises(AssertionError):
        assert_git_marketplace_source(local, "kir-kopylov/codex-team-skills")

    wrong_repo = {
        "marketplaceSource": {
            "sourceType": "git",
            "source": "https://github.com/another-owner/codex-team-skills.git",
        }
    }
    with pytest.raises(AssertionError):
        assert_git_marketplace_source(wrong_repo, "kir-kopylov/codex-team-skills")


def test_no_executable_delivery_artifacts_remain_tracked() -> None:
    forbidden_names = {
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
    }
    output = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    tracked = {Path(path).name for path in output.splitlines()}
    assert forbidden_names.isdisjoint(tracked)
