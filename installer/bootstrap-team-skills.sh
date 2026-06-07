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

# Запускаем updater БЕЗ exec, чтобы (1) всегда записать heartbeat и
# (2) явно пробросить код возврата в launchd. Раньше exec-обёртка маскировала
# реальный провал updater'а, и сбой автообновления уходил незамеченным.
STATE_DIR="$INSTALL_ROOT/state"
HEARTBEAT="$STATE_DIR/autoupdate-heartbeat.log"
mkdir -p "$STATE_DIR"

# ВНИМАНИЕ: в zsh `status` — read-only (алиас $?). Используем `rc`.
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
rc=0
"$UPDATE_SCRIPT" "$@" || rc=$?
finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

printf '%s start=%s end=%s exit=%s bootstrap=%s\n' \
  "$finished_at" "$started_at" "$finished_at" "$rc" "$BOOTSTRAP_VERSION" >> "$HEARTBEAT"

if [[ "$rc" -ne 0 ]]; then
  info "Updater завершился с ошибкой (exit=$rc); см. $HEARTBEAT и ~/Library/Logs/codex-team-skills-autoupdate.err"
fi

exit "$rc"
