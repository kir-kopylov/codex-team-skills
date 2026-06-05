from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

from conftest import ROOT


REGISTRY_HELPER = ROOT / "installer" / "team-skills-registry.py"
UPDATE_SH = ROOT / "installer" / "update-team-skills.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"


def test_registry_helper_is_idempotent_and_preserves_unrelated_config(tmp_path: Path) -> None:
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir()
    config.write_text(
        '[projects."/tmp/example"]\ntrust_level = "trusted"\n',
        encoding="utf-8",
    )

    for _ in range(2):
        subprocess.run(
            [
                sys.executable,
                str(REGISTRY_HELPER),
                "ensure",
                "--config",
                str(config),
                "--marketplace-root",
                str(tmp_path),
            ],
            check=True,
            text=True,
            capture_output=True,
        )

    text = config.read_text(encoding="utf-8")
    parsed = tomllib.loads(text)
    assert parsed["projects"]["/tmp/example"]["trust_level"] == "trusted"
    assert parsed["marketplaces"]["codex-team-skills"]["source"] == str(tmp_path)
    assert parsed["plugins"]["team-skills@codex-team-skills"]["enabled"] is True
    assert text.count("[marketplaces.codex-team-skills]") == 1
    assert text.count('[plugins."team-skills@codex-team-skills"]') == 1


def test_registry_helper_remove_only_managed_entries(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    subprocess.run(
        [
            sys.executable,
            str(REGISTRY_HELPER),
            "ensure",
            "--config",
            str(config),
            "--marketplace-root",
            str(tmp_path),
        ],
        check=True,
    )
    subprocess.run(
        [sys.executable, str(REGISTRY_HELPER), "remove", "--config", str(config)],
        check=True,
    )
    text = config.read_text(encoding="utf-8")
    tomllib.loads(text)
    assert "codex-team-skills" not in text


def test_updater_declares_no_codex_cache_contract() -> None:
    content = UPDATE_SH.read_text(encoding="utf-8")
    assert ".codex/plugins/cache" not in content
    assert "CODEX_TEAM_SKILLS_ALLOW_UNSIGNED" in content
    assert "--repair-install" in content
    assert "runtime_visibility" in content


def test_release_workflow_contains_signed_immutable_schema() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")
    build_script = (ROOT / "scripts" / "build_release_bundle.py").read_text(encoding="utf-8")
    for marker in ("latest.json", "manifest.json.sig", "latest.json.sig", "TEAM_SKILLS_SIGNING_KEY_PEM"):
        assert marker in content
    for marker in ("runtime_version", "release_id", "minimum_bootstrap_version", "team-skills-v"):
        assert marker in build_script
    assert "windows-powershell-smoke" in content
    assert "claude-sync-smoke" in content
    assert "pull-skills.sh" in content
    assert "CLAUDE_SKILLS_DIR" in content


def test_public_key_is_valid_pem() -> None:
    public_key = (ROOT / "installer" / "team-skills-public-key.pem").read_text(encoding="utf-8")
    assert public_key.startswith("-----BEGIN PUBLIC KEY-----")
    assert public_key.rstrip().endswith("-----END PUBLIC KEY-----")
