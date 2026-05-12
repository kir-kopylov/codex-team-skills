#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_NAME="team-skills"
PLUGIN_SRC="$ROOT/plugins/$PLUGIN_NAME"
PLUGIN_DEST="${CODEX_TEAM_SKILLS_PLUGIN_DIR:-$HOME/plugins/$PLUGIN_NAME}"
MARKETPLACE_PATH="${CODEX_TEAM_SKILLS_MARKETPLACE:-$HOME/.agents/plugins/marketplace.json}"

if [[ ! -f "$PLUGIN_SRC/.codex-plugin/plugin.json" ]]; then
  echo "Источник plugin не найден: $PLUGIN_SRC" >&2
  exit 1
fi

mkdir -p "$(dirname "$PLUGIN_DEST")" "$(dirname "$MARKETPLACE_PATH")"

if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete "$PLUGIN_SRC/" "$PLUGIN_DEST/"
else
  rm -rf "$PLUGIN_DEST"
  cp -R "$PLUGIN_SRC" "$PLUGIN_DEST"
fi

python3 - "$MARKETPLACE_PATH" "$PLUGIN_NAME" "$PLUGIN_DEST" <<'PY'
import json
import os
import sys
from pathlib import Path

marketplace_path = Path(sys.argv[1]).expanduser()
plugin_name = sys.argv[2]
plugin_dest = Path(sys.argv[3]).expanduser()

marketplace_root = marketplace_path.parent.parent
try:
    relative_path = "./" + os.path.relpath(plugin_dest, marketplace_root).replace(os.sep, "/")
except ValueError:
    relative_path = str(plugin_dest)

if marketplace_path.exists():
    data = json.loads(marketplace_path.read_text())
else:
    data = {
        "name": "local-team-skills",
        "interface": {"displayName": "Local Team Skills"},
        "plugins": [],
    }

data.setdefault("name", "local-team-skills")
data.setdefault("interface", {}).setdefault("displayName", "Local Team Skills")
plugins = data.setdefault("plugins", [])

entry = {
    "name": plugin_name,
    "source": {"source": "local", "path": relative_path},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    "category": "Productivity",
}

for index, existing in enumerate(plugins):
    if existing.get("name") == plugin_name:
        plugins[index] = entry
        break
else:
    plugins.append(entry)

marketplace_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
PY

echo "Plugin $PLUGIN_NAME установлен в $PLUGIN_DEST"
echo "Marketplace обновлён: $MARKETPLACE_PATH"
echo "Перезапустите Codex, чтобы он перечитал plugin."
