#!/usr/bin/env zsh
set -euo pipefail

INSTALL_ROOT="${CODEX_TEAM_SKILLS_HOME:-$HOME/Library/Application Support/CodexTeamSkills}"
BIN_DIR="$INSTALL_ROOT/bin"
UPDATE_SCRIPT="$BIN_DIR/update-team-skills.sh"
STATUS_SCRIPT="$BIN_DIR/team-skills-status.command"
SYNC_SCRIPT="$BIN_DIR/pull-skills.sh"
CLAUDE_SKILLS_DIR="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
CHECK_SKILL="${CODEX_TEAM_SKILLS_REFRESH_CHECK_SKILL:-dopsoglasheniya-po-oplate}"
RESTART_APPS="${CODEX_TEAM_SKILLS_RESTART_APPS:-Codex,Claude}"
RESTART_APPS_ENABLED=1
VALIDATE_ONLY=0

usage() {
  cat <<'USAGE'
Использование:
  refresh-team-skills.command [--no-restart] [--apps "Codex,Claude"] [--check-skill skill-name]

Делает полный post-release refresh:
  1. обновляет локальный plugin team-skills до latest release;
  2. синхронизирует repo-managed skills в Claude skills folder;
  3. проверяет наличие контрольного skill;
  4. перезапускает Codex и Claude, чтобы они перечитали skills.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-restart)
      RESTART_APPS_ENABLED=0
      shift
      ;;
    --apps)
      RESTART_APPS="${2:-}"
      shift 2
      ;;
    --check-skill)
      CHECK_SKILL="${2:-}"
      shift 2
      ;;
    --claude-skills-dir)
      CLAUDE_SKILLS_DIR="${2:-}"
      shift 2
      ;;
    --validate-only)
      VALIDATE_ONLY=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      printf '[team-skills-refresh] Неизвестный аргумент: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

info() {
  printf '[team-skills-refresh] %s\n' "$1"
}

require_executable() {
  local path="$1"
  local label="$2"
  if [[ ! -x "$path" ]]; then
    info "$label недоступен: $path"
    info "Сначала установите или восстановите team-skills installer."
    exit 1
  fi
}

schedule_restart_apps() {
  local cache_dir="$INSTALL_ROOT/cache"
  local log_dir="$INSTALL_ROOT/logs"
  local helper="$cache_dir/restart-runtime-apps.$$.zsh"
  local restart_log="$log_dir/team-skills-runtime-restart.log"

  mkdir -p "$cache_dir" "$log_dir"
  cat > "$helper" <<'HELPER'
#!/usr/bin/env zsh
set -euo pipefail

RESTART_APPS="${1:-Codex,Claude}"
LOG_PATH="${2:-/tmp/team-skills-runtime-restart.log}"

log() {
  printf '%s [team-skills-restart] %s\n' "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "$1" >> "$LOG_PATH"
}

app_is_running() {
  local app="$1"
  /usr/bin/osascript - "$app" <<'OSA'
on run argv
  set appName to item 1 of argv
  tell application "System Events"
    if exists process appName then
      return "yes"
    else
      return "no"
    end if
  end tell
end run
OSA
}

quit_app_if_running() {
  local app="$1"
  if [[ "$(app_is_running "$app")" != "yes" ]]; then
    return 0
  fi

  log "Закрываю $app."
  /usr/bin/osascript - "$app" <<'OSA'
on run argv
  set appName to item 1 of argv
  tell application appName to quit
end run
OSA

  local attempt
  for attempt in {1..20}; do
    if [[ "$(app_is_running "$app")" != "yes" ]]; then
      return 0
    fi
    sleep 0.5
  done

  log "$app всё ещё запущен; продолжаю без принудительного kill."
}

open_app() {
  local app="$1"
  log "Открываю $app."
  if ! /usr/bin/open -a "$app" >/dev/null 2>&1; then
    log "Не удалось открыть $app через open -a; возможно приложение не установлено под этим именем."
  fi
}

restart_apps() {
  local raw_app app
  for raw_app in "${(@s:,:)RESTART_APPS}"; do
    app="$(printf '%s' "$raw_app" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [[ -n "$app" ]] || continue
    quit_app_if_running "$app"
  done

  for raw_app in "${(@s:,:)RESTART_APPS}"; do
    app="$(printf '%s' "$raw_app" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [[ -n "$app" ]] || continue
    open_app "$app"
  done
}

sleep 1
log "Запускаю detached restart apps: $RESTART_APPS."
restart_apps
rm -f "$0" || true
HELPER

  chmod +x "$helper"
  nohup /bin/zsh "$helper" "$RESTART_APPS" "$restart_log" >/dev/null 2>&1 </dev/null &
  disown
  info "Detached restart helper запущен; log: $restart_log"
}

if [[ "$VALIDATE_ONLY" == "1" ]]; then
  info "ValidateOnly: refresh-team-skills.command parsed and initialized."
  exit 0
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  info "Эта automation-команда поддерживает macOS desktop runtime."
  exit 1
fi

require_executable "$UPDATE_SCRIPT" "update-team-skills.sh"

info "1/4 Обновляю локальный plugin team-skills до latest release."
"$UPDATE_SCRIPT"

require_executable "$SYNC_SCRIPT" "pull-skills.sh"

info "2/4 Синхронизирую repo-managed skills в Claude skills folder."
CLAUDE_SKILLS_DIR="$CLAUDE_SKILLS_DIR" "$SYNC_SCRIPT"

if [[ -n "$CHECK_SKILL" ]]; then
  if [[ ! -f "$CLAUDE_SKILLS_DIR/$CHECK_SKILL/SKILL.md" ]]; then
    info "Контрольный skill не найден после Claude sync: $CLAUDE_SKILLS_DIR/$CHECK_SKILL/SKILL.md"
    exit 1
  fi
  info "Контрольный skill найден: $CHECK_SKILL."
fi

if [[ -x "$STATUS_SCRIPT" ]]; then
  info "3/4 Проверяю статус установленного team-skills."
  "$STATUS_SCRIPT" || true
else
  info "3/4 team-skills-status.command недоступен; пропускаю status."
fi

if [[ "$RESTART_APPS_ENABLED" == "1" ]]; then
  info "4/4 Планирую detached restart Codex/Claude desktop apps: $RESTART_APPS."
  schedule_restart_apps
else
  info "4/4 Restart отключён аргументом --no-restart."
fi

info "Готово: локальные team-skills обновлены, Claude skills folder синхронизирован, runtime restart запущен или явно пропущен."
