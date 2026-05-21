#!/usr/bin/env zsh
set -euo pipefail

INSTALL_ROOT="${CODEX_TEAM_SKILLS_HOME:-$HOME/Library/Application Support/CodexTeamSkills}"
STATE_PATH="$INSTALL_ROOT/state/state.json"
BIN_DIR="$INSTALL_ROOT/bin"
PLUGIN_DEST="${CODEX_TEAM_SKILLS_PLUGIN_DIR:-$HOME/plugins/team-skills}"
MARKETPLACE_PATH="${CODEX_TEAM_SKILLS_MARKETPLACE:-$HOME/.agents/plugins/marketplace.json}"
CODEX_CONFIG_PATH="${CODEX_TEAM_SKILLS_CODEX_CONFIG:-$HOME/.codex/config.toml}"
REGISTRY_HELPER="${CODEX_TEAM_SKILLS_REGISTRY_HELPER:-$BIN_DIR/team-skills-registry.py}"
PLIST_PATH="$HOME/Library/LaunchAgents/com.codex-team-skills.autoupdate.plist"

printf '[team-skills] Plugin path: %s\n' "$PLUGIN_DEST"
if [[ -f "$PLUGIN_DEST/.codex-plugin/plugin.json" ]]; then
  printf '[team-skills] Plugin установлен: да\n'
else
  printf '[team-skills] Plugin установлен: нет\n'
fi
printf '[team-skills] Marketplace: %s\n' "$MARKETPLACE_PATH"
printf '[team-skills] Codex config: %s\n' "$CODEX_CONFIG_PATH"
if [[ -f "$REGISTRY_HELPER" ]] && command -v python3 >/dev/null 2>&1; then
  printf '[team-skills] Codex registry:\n'
  python3 "$REGISTRY_HELPER" status --config "$CODEX_CONFIG_PATH" || true
else
  printf '[team-skills] Codex registry: helper недоступен\n'
fi
if [[ -f "$PLIST_PATH" ]]; then
  printf '[team-skills] Автообновление включено: да\n'
else
  printf '[team-skills] Автообновление включено: нет\n'
fi
if [[ -f "$STATE_PATH" ]]; then
  printf '[team-skills] Последнее успешное обновление:\n'
  cat "$STATE_PATH"
else
  printf '[team-skills] Ещё нет записи о успешном обновлении.\n'
fi
printf '[team-skills] Runtime visibility: requires Codex restart; cannot be proven from shell.\n'
