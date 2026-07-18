#!/usr/bin/env zsh
set -euo pipefail

PLUGIN_NAME="team-skills"
INSTALL_ROOT="${CODEX_TEAM_SKILLS_HOME:-$HOME/Library/Application Support/CodexTeamSkills}"
BIN_DIR="$INSTALL_ROOT/bin"
PLUGIN_DEST="${CODEX_TEAM_SKILLS_PLUGIN_DIR:-$HOME/plugins/team-skills}"
MARKETPLACE_PATH="${CODEX_TEAM_SKILLS_MARKETPLACE:-$HOME/.agents/plugins/marketplace.json}"
CODEX_CONFIG_PATH="${CODEX_TEAM_SKILLS_CODEX_CONFIG:-$HOME/.codex/config.toml}"
CODEX_PLUGIN_CACHE_DIR="${CODEX_TEAM_SKILLS_CODEX_PLUGIN_CACHE_DIR:-$HOME/.codex/plugins/cache/codex-team-skills}"
REGISTRY_HELPER="${CODEX_TEAM_SKILLS_REGISTRY_HELPER:-$BIN_DIR/team-skills-registry.py}"
PLIST_PATH="$HOME/Library/LaunchAgents/com.codex-team-skills.autoupdate.plist"

info() {
  printf '[team-skills] %s\n' "$1"
}

fail() {
  info "$1"
  exit 1
}

safe_remove_tree() {
  local target_path="$1"
  local resolved="${target_path:A}"
  local home_resolved="${HOME:A}"
  [[ -n "$resolved" && "$resolved" != "/" && "$resolved" != "$home_resolved" ]] || \
    fail "Небезопасный путь для удаления: $target_path"
  rm -rf -- "$target_path"
}

command -v python3 >/dev/null 2>&1 || fail "Для полного удаления нужен Python 3.11 или новее."
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' || \
  fail "Для полного удаления нужен Python 3.11 или новее."

LEGACY_LAUNCHD_SERVICE="gui/$UID/com.codex-team-skills.autoupdate"
launchctl unload "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl bootout "$LEGACY_LAUNCHD_SERVICE" >/dev/null 2>&1 || true
rm -f "$PLIST_PATH"
if launchctl print "$LEGACY_LAUNCHD_SERVICE" >/dev/null 2>&1; then
  fail "Не удалось остановить старый LaunchAgent Team Skills."
fi
info "Старый LaunchAgent Team Skills удалён."

safe_remove_tree "$PLUGIN_DEST"
info "Локальный plugin team-skills удалён."

if [[ -f "$MARKETPLACE_PATH" ]]; then
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

if [[ -f "$CODEX_CONFIG_PATH" ]]; then
  [[ -f "$REGISTRY_HELPER" ]] || fail "Не найден helper для удаления записи из Codex registry: $REGISTRY_HELPER"
  python3 "$REGISTRY_HELPER" remove --config "$CODEX_CONFIG_PATH" >/dev/null
  info "Запись team-skills удалена из Codex registry."
fi

if [[ -d "$CODEX_PLUGIN_CACHE_DIR" ]]; then
  safe_remove_tree "$CODEX_PLUGIN_CACHE_DIR"
  info "Codex plugin cache team-skills удалён."
fi

safe_remove_tree "$INSTALL_ROOT"
info "Локальные служебные файлы Team Skills удалены."
info "Удаление завершено. Перезапустите Codex, чтобы он перечитал список plugin."
