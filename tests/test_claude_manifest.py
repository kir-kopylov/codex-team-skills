from __future__ import annotations

import json

from conftest import PLUGIN_DIR, ROOT


def test_claude_marketplace_manifest_is_valid() -> None:
    path = ROOT / ".claude-plugin" / "marketplace.json"
    marketplace = json.loads(path.read_text(encoding="utf-8"))

    assert marketplace["name"] == "codex-team-skills"

    plugins = marketplace["plugins"]
    assert isinstance(plugins, list) and len(plugins) == 1

    entry = plugins[0]
    assert entry["name"] == "team-skills"
    # Claude-формат source — строка-путь (в отличие от Codex, где это объект)
    assert entry["source"] == "./plugins/team-skills"
    assert PLUGIN_DIR.is_dir()


def test_claude_plugin_manifest_is_valid() -> None:
    path = PLUGIN_DIR / ".claude-plugin" / "plugin.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))

    assert manifest["name"] == "team-skills"

    description = manifest.get("description")
    assert isinstance(description, str) and description.strip()

    # version намеренно опущена: Claude Code определяет обновление по version
    # раньше git SHA, поэтому фиксированная версия мешает доставке правок skills/.
    assert "version" not in manifest

    assert (PLUGIN_DIR / "skills").is_dir()


def test_claude_and_codex_manifests_agree() -> None:
    claude_market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    codex_market = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
    assert claude_market["name"] == codex_market["name"] == "codex-team-skills"

    claude_plugin = json.loads((PLUGIN_DIR / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    codex_plugin = json.loads((PLUGIN_DIR / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert claude_plugin["name"] == codex_plugin["name"] == "team-skills"
