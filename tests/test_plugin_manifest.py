from __future__ import annotations

import json
import re

from conftest import PLUGIN_DIR, ROOT


def test_plugin_manifest_is_valid() -> None:
    path = PLUGIN_DIR / ".codex-plugin" / "plugin.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))

    assert manifest["name"] == "team-skills"
    assert re.match(r"^\d+\.\d+\.\d+$", manifest["version"])
    assert manifest["skills"] == "./skills/"
    assert (PLUGIN_DIR / "skills").is_dir()

    interface = manifest.get("interface", {})
    assert interface.get("displayName")
    assert interface.get("shortDescription")
    prompts = interface.get("defaultPrompt", [])
    assert isinstance(prompts, list) and 1 <= len(prompts) <= 3
    assert all(isinstance(prompt, str) and 1 <= len(prompt) <= 128 for prompt in prompts)


def test_marketplace_points_to_plugin() -> None:
    path = ROOT / ".agents" / "plugins" / "marketplace.json"
    marketplace = json.loads(path.read_text(encoding="utf-8"))
    entries = {entry["name"]: entry for entry in marketplace["plugins"]}

    entry = entries["team-skills"]
    assert entry["source"] == {"source": "local", "path": "./plugins/team-skills"}
    assert entry["policy"]["installation"] == "AVAILABLE"
    assert entry["policy"]["authentication"] == "ON_INSTALL"
    assert entry["category"] == "Productivity"

