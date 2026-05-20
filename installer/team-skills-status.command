#!/usr/bin/env zsh
set -euo pipefail

INSTALL_ROOT="${CODEX_TEAM_SKILLS_HOME:-$HOME/Library/Application Support/CodexTeamSkills}"
STATE_PATH="$INSTALL_ROOT/state/state.json"
PLUGIN_DEST="${CODEX_TEAM_SKILLS_PLUGIN_DIR:-$HOME/plugins/team-skills}"
MARKETPLACE_PATH="${CODEX_TEAM_SKILLS_MARKETPLACE:-$HOME/.agents/plugins/marketplace.json}"
PLIST_PATH="$HOME/Library/LaunchAgents/com.codex-team-skills.autoupdate.plist"

printf '[team-skills] Plugin path: %s\n' "$PLUGIN_DEST"
if [[ -f "$PLUGIN_DEST/.codex-plugin/plugin.json" ]]; then
  printf '[team-skills] Plugin установлен: да\n'
else
  printf '[team-skills] Plugin установлен: нет\n'
fi
printf '[team-skills] Marketplace: %s\n' "$MARKETPLACE_PATH"
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
