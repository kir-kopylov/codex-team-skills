#!/usr/bin/env zsh
set -euo pipefail

BAKED_RELEASE_TAG="__TEAM_SKILLS_RELEASE_TAG__"
VALIDATE_ONLY=0
CHILD_TIMEOUT_SECONDS=600

if [[ "$#" -gt 1 ]]; then
  printf '[team-skills] Использование: %s [--validate-only]\n' "${0:t}" >&2
  printf 'TEAM_SKILLS_MIGRATION_RESULT=INVALID_INVOCATION\n' >&2
  exit 2
fi
if [[ "$#" -eq 1 ]]; then
  case "$1" in
    --validate-only)
      VALIDATE_ONLY=1
      ;;
    *)
      printf '[team-skills] Неизвестный аргумент: %s\n' "$1" >&2
      printf '[team-skills] Использование: %s [--validate-only]\n' "${0:t}" >&2
      printf 'TEAM_SKILLS_MIGRATION_RESULT=INVALID_INVOCATION\n' >&2
      exit 2
      ;;
  esac
fi

info() {
  printf '[team-skills] %s\n' "$1"
}

if [[ "$VALIDATE_ONLY" == "1" ]]; then
  info "ValidateOnly: migrate-team-skills.command разобран без выполнения перехода."
  printf 'TEAM_SKILLS_MIGRATION_RESULT=VALIDATED\n'
  exit 0
fi

WORK_DIR=""
LOCK_DIR=""
LOCK_HELD=0

on_exit() {
  local exit_code=$?
  trap - EXIT INT TERM HUP
  set +e
  if [[ -n "$WORK_DIR" && -d "$WORK_DIR" && ! -L "$WORK_DIR" ]]; then
    rm -rf -- "$WORK_DIR"
  fi
  if [[ "$LOCK_HELD" == "1" && -n "$LOCK_DIR" && -d "$LOCK_DIR" && ! -L "$LOCK_DIR" ]]; then
    rm -f -- "$LOCK_DIR/pid"
    rmdir -- "$LOCK_DIR"
  fi
  exit "$exit_code"
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

finish_migration() {
  local outcome="$1"
  local exit_code="$2"
  local message="$3"
  info "$message"
  printf 'TEAM_SKILLS_MIGRATION_RESULT=%s\n' "$outcome"
  exit "$exit_code"
}

blocked_preflight() {
  finish_migration "BLOCKED_PREFLIGHT" 10 "$1"
}

for command_name in uname id python3 curl mktemp mkdir rm rmdir zsh; do
  command -v "$command_name" >/dev/null 2>&1 || \
    blocked_preflight "Переход не начат: не найдена обязательная команда $command_name."
done

SYSTEM_NAME="$(uname -s 2>/dev/null)" || \
  blocked_preflight "Переход не начат: не удалось определить операционную систему."
[[ "$SYSTEM_NAME" == "Darwin" ]] || \
  blocked_preflight "Переход не начат: этот файл предназначен только для macOS."

CURRENT_UID="$(id -u 2>/dev/null)" || \
  blocked_preflight "Переход не начат: не удалось определить текущего пользователя."
case "$CURRENT_UID" in
  ''|*[!0-9]*)
    blocked_preflight "Переход не начат: UID текущего пользователя некорректен."
    ;;
esac
[[ "$CURRENT_UID" != "0" ]] || \
  blocked_preflight "Переход нельзя запускать от root или через sudo."

python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' || \
  blocked_preflight "Переход не начат: нужен Python 3.11 или новее."

python3 - validate-release-tag "$BAKED_RELEASE_TAG" <<'PY' || \
  blocked_preflight "Переход не начат: migrator не привязан к корректному release tag."
import re
import sys

_, release_tag = sys.argv[1:]
if not re.fullmatch(r"team-skills-vr[0-9]+\.[0-9]+-[0-9a-f]{7}", release_tag):
    raise SystemExit(1)
PY

OVERRIDE_NAMES="$(python3 - list-overrides <<'PY'
import os

for name in sorted(os.environ):
    if name.startswith("CODEX_TEAM_SKILLS_"):
        print(name)
PY
)" || blocked_preflight "Переход не начат: не удалось проверить переменные окружения."
if [[ -n "$OVERRIDE_NAMES" ]]; then
  info "Обнаружены запрещённые path/network overrides:"
  while IFS= read -r override_name; do
    [[ -n "$override_name" ]] && info "- $override_name"
  done <<< "$OVERRIDE_NAMES"
  blocked_preflight "Удалите переменные CODEX_TEAM_SKILLS_* и запустите migrator снова."
fi

[[ -n "${HOME:-}" ]] || blocked_preflight "Переход не начат: HOME не задан."
python3 - canonical-home "$HOME" "$CURRENT_UID" <<'PY' || \
  blocked_preflight "Переход не начат: HOME не совпадает с каноническим домашним каталогом пользователя."
import os
import pwd
import sys
from pathlib import Path

_, home_raw, uid_raw = sys.argv[1:]
uid = int(uid_raw)
if not home_raw or "\n" in home_raw or "\r" in home_raw or not os.path.isabs(home_raw):
    raise SystemExit(1)
if os.path.normpath(home_raw) != home_raw:
    raise SystemExit(1)
home = Path(home_raw)
try:
    metadata = home.lstat()
except OSError:
    raise SystemExit(1)
if home.is_symlink() or not home.is_dir() or metadata.st_uid != uid:
    raise SystemExit(1)
try:
    account_home = pwd.getpwuid(uid).pw_dir
except KeyError:
    raise SystemExit(1)
if os.path.normpath(account_home) != home_raw:
    raise SystemExit(1)
if os.path.realpath(home_raw) != home_raw or os.path.realpath(account_home) != home_raw:
    raise SystemExit(1)
PY

python3 - safe-managed-paths "$HOME" <<'PY' || \
  blocked_preflight "Переход не начат: managed paths отсутствуют, имеют неверный тип или проходят через symlink."
import os
import stat
import sys
from pathlib import Path

home = Path(sys.argv[2])
targets = (
    (home / "plugins" / "team-skills", "directory"),
    (home / ".agents" / "plugins" / "marketplace.json", "file"),
    (home / ".codex" / "config.toml", "file"),
    (home / ".codex" / "plugins" / "cache" / "codex-team-skills", "directory"),
)
for target, expected_type in targets:
    cursor = home
    for part in target.relative_to(home).parts:
        cursor = cursor / part
        if not os.path.lexists(cursor):
            break
        metadata = cursor.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise SystemExit(1)
    if os.path.lexists(target):
        if expected_type == "directory" and not target.is_dir():
            raise SystemExit(1)
        if expected_type == "file" and not target.is_file():
            raise SystemExit(1)
PY

TEMP_ROOT="${TMPDIR:-/tmp}"
[[ -d "$TEMP_ROOT" ]] || \
  blocked_preflight "Переход не начат: временный каталог недоступен."
TEMP_ROOT="${TEMP_ROOT:A}"
[[ -d "$TEMP_ROOT" && ! -L "$TEMP_ROOT" ]] || \
  blocked_preflight "Переход не начат: временный каталог не удалось привести к каноническому пути."

LOCK_DIR="${TEMP_ROOT%/}/codex-team-skills-migrate-$CURRENT_UID.lock"
if ! mkdir -m 700 -- "$LOCK_DIR" 2>/dev/null; then
  if python3 - reclaim-stale-lock "$LOCK_DIR" "$CURRENT_UID" <<'PY'
import os
import stat
import sys
from pathlib import Path

_, lock_raw, uid_raw = sys.argv[1:]
uid = int(uid_raw)
lock = Path(lock_raw)
pid_path = lock / "pid"
try:
    lock_stat = lock.lstat()
    pid_stat = pid_path.lstat()
    pid_text = pid_path.read_text(encoding="ascii").strip()
except (OSError, UnicodeError):
    raise SystemExit(1)
if (
    not stat.S_ISDIR(lock_stat.st_mode)
    or lock_stat.st_uid != uid
    or not stat.S_ISREG(pid_stat.st_mode)
    or pid_stat.st_uid != uid
    or not pid_text.isdigit()
    or int(pid_text) <= 0
):
    raise SystemExit(1)
try:
    os.kill(int(pid_text), 0)
except ProcessLookupError:
    pass
except (PermissionError, OSError):
    raise SystemExit(1)
else:
    raise SystemExit(1)
try:
    pid_path.unlink()
    lock.rmdir()
except OSError:
    raise SystemExit(1)
PY
  then
    mkdir -m 700 -- "$LOCK_DIR" 2>/dev/null || \
      blocked_preflight "Переход уже выполняется: $LOCK_DIR"
  else
    blocked_preflight "Переход уже выполняется или lock нельзя безопасно переиспользовать: $LOCK_DIR"
  fi
fi
LOCK_HELD=1
if ! printf '%s\n' "$$" > "$LOCK_DIR/pid"; then
  blocked_preflight "Переход не начат: не удалось зафиксировать transient lock."
fi

WORK_DIR="$(mktemp -d "${TEMP_ROOT%/}/codex-team-skills-migrate.XXXXXX")" || \
  blocked_preflight "Переход не начат: не удалось создать временный каталог."
[[ -d "$WORK_DIR" && ! -L "$WORK_DIR" ]] || \
  blocked_preflight "Переход не начат: временный каталог не прошёл проверку."

RELEASE_BASE="https://github.com/kir-kopylov/codex-team-skills/releases/download/$BAKED_RELEASE_TAG"
CLEANUP_SCRIPT="$WORK_DIR/remove-team-skills-autoupdate.command"
INSTALLER_SCRIPT="$WORK_DIR/install-team-skills.command"

download_file() {
  local url="$1"
  local destination="$2"
  curl \
    --fail \
    --location \
    --silent \
    --show-error \
    --proto '=https' \
    --tlsv1.2 \
    --retry 2 \
    --retry-delay 2 \
    --retry-max-time 180 \
    --connect-timeout 10 \
    --max-time 60 \
    --output "$destination" \
    "$url"
}

info "Скачиваю cleanup и installer из release $BAKED_RELEASE_TAG до любых изменений продукта."
download_file "$RELEASE_BASE/remove-team-skills-autoupdate.command" "$CLEANUP_SCRIPT" || \
  blocked_preflight "Переход не начат: cleanup не удалось скачать после повторных попыток."
download_file "$RELEASE_BASE/install-team-skills.command" "$INSTALLER_SCRIPT" || \
  blocked_preflight "Переход не начат: installer не удалось скачать после повторных попыток."

for downloaded_script in "$CLEANUP_SCRIPT" "$INSTALLER_SCRIPT"; do
  [[ -s "$downloaded_script" && -f "$downloaded_script" && ! -L "$downloaded_script" ]] || \
    blocked_preflight "Переход не начат: скачанный файл ${downloaded_script:t} пуст или небезопасен."
  zsh -n "$downloaded_script" || \
    blocked_preflight "Переход не начат: скачанный файл ${downloaded_script:t} не прошёл zsh syntax check."
done

CHILD_EXIT=0
CHILD_RESULT=""
CHILD_RELEASE=""
CHILD_PLUGIN_VERSION=""
CHILD_RESULT_COUNT=0
CHILD_RELEASE_COUNT=0
CHILD_PLUGIN_VERSION_COUNT=0
CHILD_PARSE_OK=0

parse_child_output() {
  local output_file="$1"
  local line
  local value
  CHILD_RESULT=""
  CHILD_RELEASE=""
  CHILD_PLUGIN_VERSION=""
  CHILD_RESULT_COUNT=0
  CHILD_RELEASE_COUNT=0
  CHILD_PLUGIN_VERSION_COUNT=0
  CHILD_PARSE_OK=1

  while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
      TEAM_SKILLS_RESULT=*)
        value="${line#TEAM_SKILLS_RESULT=}"
        (( CHILD_RESULT_COUNT += 1 ))
        case "$value" in
          ''|*[!A-Z0-9_]*) CHILD_PARSE_OK=0 ;;
          *) CHILD_RESULT="$value" ;;
        esac
        ;;
      TEAM_SKILLS_RELEASE=*)
        value="${line#TEAM_SKILLS_RELEASE=}"
        (( CHILD_RELEASE_COUNT += 1 ))
        case "$value" in
          ''|*[!A-Za-z0-9._-]*) CHILD_PARSE_OK=0 ;;
          *) CHILD_RELEASE="$value" ;;
        esac
        ;;
      TEAM_SKILLS_PLUGIN_VERSION=*)
        value="${line#TEAM_SKILLS_PLUGIN_VERSION=}"
        (( CHILD_PLUGIN_VERSION_COUNT += 1 ))
        case "$value" in
          ''|*[!A-Za-z0-9.+-]*) CHILD_PARSE_OK=0 ;;
          *) CHILD_PLUGIN_VERSION="$value" ;;
        esac
        ;;
    esac
  done < "$output_file"

  [[ "$CHILD_RESULT_COUNT" == "1" ]] || CHILD_PARSE_OK=0
  (( CHILD_RELEASE_COUNT <= 1 )) || CHILD_PARSE_OK=0
  (( CHILD_PLUGIN_VERSION_COUNT <= 1 )) || CHILD_PARSE_OK=0
}

run_child() {
  local capture_name="$1"
  local child_script="$2"
  local output_file="$WORK_DIR/$capture_name.output"
  shift 2

  if python3 - run-child "$CHILD_TIMEOUT_SECONDS" "$output_file" "$child_script" "$@" <<'PY'
import os
import signal
import subprocess
import sys

_, timeout_raw, output_path, child_script, *arguments = sys.argv[1:]
timeout = int(timeout_raw)
with open(output_path, "wb") as output:
    process = subprocess.Popen(
        ["zsh", child_script, *arguments],
        stdout=output,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        return_code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        output.write(
            f"[team-skills] Child process превысил timeout {timeout} секунд.\n".encode("utf-8")
        )
        output.flush()
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        raise SystemExit(124)
raise SystemExit(return_code)
PY
  then
    CHILD_EXIT=0
  else
    CHILD_EXIT=$?
  fi

  while IFS= read -r output_line || [[ -n "$output_line" ]]; do
    printf '%s\n' "$output_line"
  done < "$output_file"
  parse_child_output "$output_file"
}

cleanup_contract_valid() {
  [[ "$CHILD_PARSE_OK" == "1" && "$CHILD_RELEASE_COUNT" == "0" && "$CHILD_PLUGIN_VERSION_COUNT" == "0" ]]
}

finish_cleanup_failure() {
  local phase="$1"
  local mutation_started="${2:-0}"
  if cleanup_contract_valid && [[ "$mutation_started" == "0" && "$CHILD_RESULT" == "REFUSED_UNSAFE" && "$CHILD_EXIT" == "3" ]]; then
    finish_migration "REFUSED_UNSAFE" 3 "$phase: cleanup отказался продолжать из-за неоднозначного или небезопасного scope."
  fi
  finish_migration "CLEANUP_INCOMPLETE" 4 "$phase: результат cleanup не совпал с машинным контрактом или postcondition не достигнуты."
}

info "Проверяю legacy updater без изменений."
run_child "cleanup-initial-dry-run" "$CLEANUP_SCRIPT" --dry-run
if ! cleanup_contract_valid; then
  finish_cleanup_failure "Первый dry-run"
fi

case "$CHILD_RESULT:$CHILD_EXIT" in
  NOT_FOUND:0)
    ;;
  DRY_RUN_SAFE:0)
    info "Legacy updater точно атрибутирован; запускаю официальный cleanup."
    run_child "cleanup-initial-apply" "$CLEANUP_SCRIPT" --apply
    if ! cleanup_contract_valid; then
      finish_cleanup_failure "Первый apply" 1
    fi
    case "$CHILD_RESULT:$CHILD_EXIT" in
      CLEANED:0|NOT_FOUND:0)
        ;;
      *)
        finish_cleanup_failure "Первый apply" 1
        ;;
    esac
    ;;
  *)
    finish_cleanup_failure "Первый dry-run"
    ;;
esac

info "Запускаю installer release $BAKED_RELEASE_TAG один раз."
run_child "installer" "$INSTALLER_SCRIPT" --manifest-url "$RELEASE_BASE/manifest.json"
if [[ "$CHILD_PARSE_OK" != "1" || "$CHILD_RESULT" != "INSTALLED" || "$CHILD_EXIT" != "0" || \
      "$CHILD_RELEASE_COUNT" != "1" || "$CHILD_RELEASE" != "$BAKED_RELEASE_TAG" || \
      "$CHILD_PLUGIN_VERSION_COUNT" != "1" ]]; then
  finish_migration "LEGACY_REMOVED_INSTALL_PENDING" 5 \
    "Installer не доказал установку точного release; legacy updater отсутствует, установка требует отдельного повторного запуска."
fi

PLUGIN_MANIFEST="$HOME/plugins/team-skills/.codex-plugin/plugin.json"
CODEX_CACHE="$HOME/.codex/plugins/cache/codex-team-skills"
if ! python3 - verify-installed-plugin "$PLUGIN_MANIFEST" "$BAKED_RELEASE_TAG" "$CHILD_PLUGIN_VERSION" <<'PY'
import json
import sys
from pathlib import Path

_, manifest_raw, expected_release, expected_version = sys.argv[1:]
manifest_path = Path(manifest_raw)
plugin_root = manifest_path.parent.parent
if plugin_root.is_symlink() or manifest_path.is_symlink() or not manifest_path.is_file():
    raise SystemExit(1)
try:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
except (OSError, UnicodeError, json.JSONDecodeError):
    raise SystemExit(1)
if not isinstance(payload, dict):
    raise SystemExit(1)
version = payload.get("version")
if (
    payload.get("name") != "team-skills"
    or payload.get("release_tag") != expected_release
    or not isinstance(version, str)
    or version != expected_version
):
    raise SystemExit(1)
PY
then
  finish_migration "LEGACY_REMOVED_INSTALL_PENDING" 5 \
    "Installer завершился, но точный release не подтверждён в plugin manifest на диске."
fi
if [[ -e "$CODEX_CACHE" || -L "$CODEX_CACHE" ]]; then
  finish_migration "LEGACY_REMOVED_INSTALL_PENDING" 5 \
    "Installer завершился, но старый Codex plugin cache не удалён."
fi

info "Повторно проверяю, что installer не создал legacy updater."
run_child "cleanup-final-dry-run" "$CLEANUP_SCRIPT" --dry-run
if ! cleanup_contract_valid; then
  finish_cleanup_failure "Финальный dry-run" 1
fi

case "$CHILD_RESULT:$CHILD_EXIT" in
  NOT_FOUND:0)
    finish_migration "MIGRATED_RESTART_REQUIRED" 0 \
      "Точный release установлен, cache удалён, legacy updater отсутствует. Полностью перезапустите Codex."
    ;;
  DRY_RUN_SAFE:0)
    info "После installer снова обнаружен legacy updater; очищаю его и запрещаю завершение rollout."
    run_child "cleanup-regression-apply" "$CLEANUP_SCRIPT" --apply
    if ! cleanup_contract_valid; then
      finish_cleanup_failure "Очистка post-install регрессии" 1
    fi
    case "$CHILD_RESULT:$CHILD_EXIT" in
      CLEANED:0|NOT_FOUND:0)
        finish_migration "INSTALLER_REGRESSION_CLEANED" 6 \
          "После installer обнаружен legacy updater; cleanup удалил его, но этот release нельзя считать готовым к rollout."
        ;;
      *)
        finish_cleanup_failure "Очистка post-install регрессии" 1
        ;;
    esac
    ;;
  *)
    finish_cleanup_failure "Финальный dry-run" 1
    ;;
esac
