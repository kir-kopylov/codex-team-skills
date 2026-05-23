#!/usr/bin/env zsh
set -euo pipefail

BOOTSTRAP_VERSION="1.0.0"
INSTALL_ROOT="${CODEX_TEAM_SKILLS_HOME:-$HOME/Library/Application Support/CodexTeamSkills}"
BIN_DIR="$INSTALL_ROOT/bin"
UPDATE_SCRIPT="$BIN_DIR/update-team-skills.sh"
NEXT_UPDATE_SCRIPT="$UPDATE_SCRIPT.next"

info() {
  printf '[team-skills] %s\n' "$1"
}

if [[ ! -x "$UPDATE_SCRIPT" ]]; then
  info "Updater не найден: $UPDATE_SCRIPT"
  info "Запустите installer заново, чтобы восстановить support files."
  exit 1
fi

if [[ -f "$NEXT_UPDATE_SCRIPT" ]]; then
  mv "$NEXT_UPDATE_SCRIPT" "$UPDATE_SCRIPT"
  chmod +x "$UPDATE_SCRIPT"
  info "Updater обновлён из staged .next версии."
fi

export CODEX_TEAM_SKILLS_BOOTSTRAP_VERSION="$BOOTSTRAP_VERSION"
exec "$UPDATE_SCRIPT" "$@"
