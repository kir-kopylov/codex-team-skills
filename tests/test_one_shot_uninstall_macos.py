from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import ROOT


SCRIPT = ROOT / "installer" / "uninstall-team-skills.command"
pytestmark = pytest.mark.skipif(shutil.which("zsh") is None, reason="для проверки нужен zsh")


def run_uninstaller(home: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["HOME"] = str(home)
    return subprocess.run(
        ["zsh", str(SCRIPT)],
        env=environment,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def create_installation(home: Path) -> tuple[Path, Path, Path, Path]:
    plugin = home / "plugins" / "team-skills"
    plugin.mkdir(parents=True)
    (plugin / "marker.txt").write_text("plugin\n", encoding="utf-8")

    cache = home / ".codex" / "plugins" / "cache" / "codex-team-skills"
    cache.mkdir(parents=True)
    (cache / "cache.txt").write_text("cache\n", encoding="utf-8")

    marketplace = home / ".agents" / "plugins" / "marketplace.json"
    marketplace.parent.mkdir(parents=True)
    marketplace.write_text(
        json.dumps(
            {
                "plugins": [
                    {"name": "team-skills"},
                    {"name": "keep-me"},
                ]
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    config = home / ".codex" / "config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        '[plugins."keep-me@local"]\n'
        "enabled = true\n\n"
        "# BEGIN codex-team-skills managed block\n"
        "[marketplaces.codex-team-skills]\n"
        'source = "/tmp/example"\n\n'
        '[plugins."team-skills@codex-team-skills"]\n'
        "enabled = true\n"
        "# END codex-team-skills managed block\n",
        encoding="utf-8",
    )
    return plugin, cache, marketplace, config


def test_uninstaller_removes_only_active_product_artifacts(tmp_path: Path) -> None:
    home = tmp_path / "home"
    plugin, cache, marketplace, config = create_installation(home)

    result = run_uninstaller(home)

    assert result.returncode == 0, result.stdout + result.stderr
    assert not plugin.exists()
    assert not cache.exists()
    assert [entry["name"] for entry in json.loads(marketplace.read_text(encoding="utf-8"))["plugins"]] == ["keep-me"]
    config_text = config.read_text(encoding="utf-8")
    assert "team-skills@codex-team-skills" not in config_text
    assert "keep-me@local" in config_text
    assert list(marketplace.parent.glob("marketplace.json.codex-team-skills.bak.*"))
    assert list(config.parent.glob("config.toml.codex-team-skills.bak.*"))
    assert not (home / "Library" / "Application Support" / "CodexTeamSkills").exists()


def test_uninstaller_refuses_while_legacy_updater_marker_exists(tmp_path: Path) -> None:
    home = tmp_path / "home"
    plugin, _, _, _ = create_installation(home)
    marker = home / "Library" / "Application Support" / "CodexTeamSkills" / "bin" / "bootstrap-team-skills.sh"
    marker.parent.mkdir(parents=True)
    marker.write_text("#!/usr/bin/env zsh\n", encoding="utf-8")

    result = run_uninstaller(home)

    assert result.returncode == 1
    assert "remove-team-skills-autoupdate.command --dry-run" in result.stdout
    assert plugin.exists()
