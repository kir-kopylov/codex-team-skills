#!/usr/bin/env zsh
set -euo pipefail

PLUGIN_NAME="team-skills"
INSTALL_ROOT="${CODEX_TEAM_SKILLS_HOME:-$HOME/Library/Application Support/CodexTeamSkills}"
BIN_DIR="$INSTALL_ROOT/bin"
PLUGIN_DEST="${CODEX_TEAM_SKILLS_PLUGIN_DIR:-$HOME/plugins/team-skills}"
MARKETPLACE_PATH="${CODEX_TEAM_SKILLS_MARKETPLACE:-$HOME/.agents/plugins/marketplace.json}"
CODEX_CONFIG_PATH="${CODEX_TEAM_SKILLS_CODEX_CONFIG:-$HOME/.codex/config.toml}"
REGISTRY_HELPER="${CODEX_TEAM_SKILLS_REGISTRY_HELPER:-$BIN_DIR/team-skills-registry.py}"
PLIST_PATH="$HOME/Library/LaunchAgents/com.codex-team-skills.autoupdate.plist"

info() {
  printf '[team-skills] %s\n' "$1"
}

launchctl unload "$PLIST_PATH" >/dev/null 2>&1 || true
rm -f "$PLIST_PATH"
info "Автообновление удалено из LaunchAgent."

rm -rf "$PLUGIN_DEST"
info "Локальный plugin team-skills удалён."

if [[ -f "$MARKETPLACE_PATH" ]] && command -v python3 >/dev/null 2>&1; then
  python3 - "$MARKETPLACE_PATH" "$PLUGIN_NAME" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1]).expanduser()
plugin_name = sys.argv[2]
data = json.loads(path.read_text(encoding="utf-8"))
data["plugins"] = [entry for entry in data.get("plugins", []) if entry.get("name") != plugin_name]
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
  info "Запись team-skills удалена из marketplace."
fi

if [[ -f "$REGISTRY_HELPER" ]] && command -v python3 >/dev/null 2>&1; then
  python3 "$REGISTRY_HELPER" remove --config "$CODEX_CONFIG_PATH" >/dev/null || true
  info "Запись team-skills удалена из Codex registry."
fi

rm -rf "$INSTALL_ROOT"
info "Удаление завершено. Перезапустите Codex, чтобы он перечитал список plugin."
