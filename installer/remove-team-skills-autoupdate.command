#!/usr/bin/env zsh
set -u
set -o pipefail

LABEL="com.codex-team-skills.autoupdate"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"
SERVICE_TARGET="gui/$UID/$LABEL"
CANONICAL_ROOT="$HOME/Library/Application Support/CodexTeamSkills"
STDOUT_LOG="$HOME/Library/Logs/codex-team-skills-autoupdate.log"
STDERR_LOG="$HOME/Library/Logs/codex-team-skills-autoupdate.err"

DEFAULT_PLUGIN_PATH="$HOME/plugins/team-skills"
DEFAULT_MARKETPLACE_PATH="$HOME/.agents/plugins/marketplace.json"
DEFAULT_CONFIG_PATH="$HOME/.codex/config.toml"
DEFAULT_CACHE_PATH="$HOME/.codex/plugins/cache/codex-team-skills"

PLUGIN_PATH="${CODEX_TEAM_SKILLS_PLUGIN_DIR:-$DEFAULT_PLUGIN_PATH}"
MARKETPLACE_ROOT="${CODEX_TEAM_SKILLS_MARKETPLACE_ROOT:-$HOME}"
MARKETPLACE_PATH="${CODEX_TEAM_SKILLS_MARKETPLACE:-$MARKETPLACE_ROOT/.agents/plugins/marketplace.json}"
CONFIG_PATH="${CODEX_TEAM_SKILLS_CODEX_CONFIG:-$DEFAULT_CONFIG_PATH}"
CACHE_PATH="${CODEX_TEAM_SKILLS_CODEX_PLUGIN_CACHE_DIR:-$DEFAULT_CACHE_PATH}"

MODE=""
if [[ "$#" -ne 1 ]]; then
  printf '[team-skills] Использование: %s --dry-run | --apply\n' "${0:t}" >&2
  exit 2
fi

case "$1" in
  --dry-run)
    MODE="dry-run"
    ;;
  --apply)
    MODE="apply"
    ;;
  *)
    printf '[team-skills] Неизвестный аргумент: %s\n' "$1" >&2
    printf '[team-skills] Использование: %s --dry-run | --apply\n' "${0:t}" >&2
    exit 2
    ;;
esac

info() {
  printf '[team-skills] %s\n' "$1"
}

unexpected() {
  info "Очистка запрещена: $1"
  info "Результат: REFUSED_UNSAFE"
  exit 3
}

for command_name in python3 launchctl ps awk rm sleep; do
  command -v "$command_name" >/dev/null 2>&1 || \
    unexpected "не найдена обязательная команда $command_name."
done

path_fingerprint() {
  python3 - "$1" <<'PY'
import hashlib
import os
import stat
import sys
from pathlib import Path

root = Path(sys.argv[1])

if not os.path.lexists(root):
    print("ABSENT")
    raise SystemExit(0)

def record(digest, kind, relative, payload=b""):
    digest.update(kind)
    digest.update(b"\0")
    digest.update(os.fsencode(relative))
    digest.update(b"\0")
    digest.update(payload)
    digest.update(b"\0")

if root.is_symlink():
    digest = hashlib.sha256()
    record(digest, b"L", ".", os.fsencode(os.readlink(root)))
    print(digest.hexdigest())
    raise SystemExit(0)

if root.is_file():
    print(hashlib.sha256(root.read_bytes()).hexdigest())
    raise SystemExit(0)

if not root.is_dir():
    digest = hashlib.sha256()
    record(digest, b"O", ".", str(root.lstat().st_mode).encode("ascii"))
    print(digest.hexdigest())
    raise SystemExit(0)

digest = hashlib.sha256()
record(digest, b"D", ".")
for current, directories, files in os.walk(root, topdown=True, followlinks=False):
    directories.sort()
    files.sort()
    current_path = Path(current)
    entries = [(name, True) for name in directories] + [(name, False) for name in files]
    for name, is_directory_hint in sorted(entries):
        path = current_path / name
        relative = path.relative_to(root).as_posix()
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            record(digest, b"L", relative, os.fsencode(os.readlink(path)))
        elif stat.S_ISDIR(mode):
            record(digest, b"D", relative)
        elif stat.S_ISREG(mode):
            record(digest, b"F", relative, hashlib.sha256(path.read_bytes()).digest())
        else:
            record(digest, b"O", relative, str(mode).encode("ascii"))

print(digest.hexdigest())
PY
}

capture_protected() {
  local prefix="$1"
  local value

  value="$(path_fingerprint "$PLUGIN_PATH")" || unexpected "не удалось вычислить SHA-256 plugin."
  typeset -g "${prefix}_PLUGIN=$value"
  value="$(path_fingerprint "$MARKETPLACE_PATH")" || unexpected "не удалось вычислить SHA-256 marketplace."
  typeset -g "${prefix}_MARKETPLACE=$value"
  value="$(path_fingerprint "$CONFIG_PATH")" || unexpected "не удалось вычислить SHA-256 config."
  typeset -g "${prefix}_CONFIG=$value"
  value="$(path_fingerprint "$CACHE_PATH")" || unexpected "не удалось вычислить SHA-256 active cache."
  typeset -g "${prefix}_CACHE=$value"
  value="$(protected_set_fingerprint)" || unexpected "не удалось вычислить SHA-256 защищённого набора."
  typeset -g "${prefix}_PROTECTED_SET=$value"
}

protected_set_fingerprint() {
  local protected_path
  local fingerprint
  local pairs=()
  for protected_path in "${PROTECTED_PATHS[@]}"; do
    fingerprint="$(path_fingerprint "$protected_path")" || return 1
    pairs+=("$protected_path" "$fingerprint")
  done
  python3 - "${pairs[@]}" <<'PY'
import hashlib
import json
import sys

arguments = sys.argv[1:]
if len(arguments) % 2:
    raise SystemExit("непарный protected fingerprint")
items = {}
for index in range(0, len(arguments), 2):
    items[arguments[index]] = arguments[index + 1]
payload = json.dumps(sorted(items.items()), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
print(hashlib.sha256(payload).hexdigest())
PY
}

service_is_loaded() {
  launchctl print "$SERVICE_TARGET" >/dev/null 2>&1
}

scheduler_count() {
  local plist_present=0
  local service_present=0
  [[ -e "$PLIST_PATH" || -L "$PLIST_PATH" ]] && plist_present=1
  service_is_loaded && service_present=1
  if (( plist_present || service_present )); then
    printf '1\n'
  else
    printf '0\n'
  fi
}

root_present() {
  local root="$1"
  if [[ -n "$root" && ( -e "$root" || -L "$root" ) ]]; then
    printf 'true\n'
  else
    printf 'false\n'
  fi
}

list_updater_pids() {
  local root="$1"
  [[ -n "$root" ]] || return 0
  python3 - "$root" <<'PY'
import os
import re
import subprocess
import sys

root = sys.argv[1]
names = (
    "bootstrap-team-skills.sh",
    "update-team-skills.sh",
    "update-team-skills.sh.next",
    "refresh-team-skills.command",
    "refresh-team-skills.command.next",
    "update-team-skills-with-cache-reset.sh",
)
paths = [os.path.join(root, "bin", name) for name in names]
shell_prefix = re.compile(r"^(?:/bin/(?:zsh|sh|bash)|(?:zsh|sh|bash))\s+(.*)$")

def is_exact_script_command(arguments, path):
    candidates = (path, "\"" + path + "\"", chr(39) + path + chr(39))
    return any(arguments == candidate or arguments.startswith(candidate + " ") for candidate in candidates)

completed = subprocess.run(
    ["ps", "-axo", "pid=,command="],
    check=False,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)
if completed.returncode:
    sys.stderr.write(completed.stderr)
    raise SystemExit(completed.returncode)

for raw_line in completed.stdout.splitlines():
    match = re.match(r"^\s*(\d+)\s+(.*)$", raw_line)
    if not match:
        continue
    pid, command = match.groups()
    shell_match = shell_prefix.match(command)
    if shell_match and any(is_exact_script_command(shell_match.group(1), path) for path in paths):
        print(pid)
PY
}

updater_process_count() {
  local root="$1"
  local pids
  pids="$(list_updater_pids "$root")" || return 1
  if [[ -z "$pids" ]]; then
    printf '0\n'
  else
    printf '%s\n' "$pids" | awk 'NF {count += 1} END {print count + 0}'
  fi
}

LOADED=0
service_is_loaded && LOADED=1

run_discovery() {
  python3 - "$HOME" "$PLIST_PATH" "$CANONICAL_ROOT" "$LOADED" \
  "$PLUGIN_PATH" "$MARKETPLACE_PATH" "$CONFIG_PATH" "$CACHE_PATH" \
  "$DEFAULT_PLUGIN_PATH" "$DEFAULT_MARKETPLACE_PATH" "$DEFAULT_CONFIG_PATH" "$DEFAULT_CACHE_PATH" \
  "$STDOUT_LOG" "$STDERR_LOG" <<'PY'
import fnmatch
import json
import os
import plistlib
import re
import stat
import sys
from pathlib import Path

(
    home_raw,
    plist_raw,
    canonical_raw,
    loaded_raw,
    plugin_raw,
    marketplace_raw,
    config_raw,
    cache_raw,
    default_plugin_raw,
    default_marketplace_raw,
    default_config_raw,
    default_cache_raw,
    stdout_log_raw,
    stderr_log_raw,
) = sys.argv[1:]

home = Path(home_raw)
plist_path = Path(plist_raw)
canonical_root = Path(canonical_raw)
service_loaded = loaded_raw == "1"
protected = [
    Path(plugin_raw),
    Path(marketplace_raw),
    Path(config_raw),
    Path(cache_raw),
    Path(default_plugin_raw),
    Path(default_marketplace_raw),
    Path(default_config_raw),
    Path(default_cache_raw),
]
state_protected = []

allowed_bin_names = {
    "bootstrap-team-skills.ps1",
    "bootstrap-team-skills.sh",
    "install-team-skills.cmd",
    "install-team-skills.command",
    "install-team-skills.ps1",
    "pull-skills.sh",
    "refresh-team-skills.command",
    "refresh-team-skills.command.next",
    "team-skills-public-key.pem",
    "team-skills-registry.py",
    "team-skills-status.command",
    "team-skills-status.ps1",
    "uninstall-team-skills.command",
    "uninstall-team-skills.ps1",
    "update-team-skills.ps1",
    "update-team-skills.ps1.next",
    "update-team-skills.sh",
    "update-team-skills.sh.next",
    "update-team-skills-with-cache-reset.sh",
}
allowed_bin_directory_names = {"__pycache__"}
allowed_registry_bytecode = re.compile(
    r"^team-skills-registry\.cpython-[0-9]+\.pyc$"
)
allowed_root_names = {"bin", "cache", "state", "logs"}
scheduler_scripts = {"bootstrap-team-skills.sh", "update-team-skills.sh"}
updater_markers = {
    "bootstrap-team-skills.sh",
    "update-team-skills.sh",
    "update-team-skills.sh.next",
    "refresh-team-skills.command",
    "refresh-team-skills.command.next",
    "update-team-skills-with-cache-reset.sh",
}
recovery_patterns = ("*.backup.*", "*.previous.*", "*.stale.*")
state_path_keys = (
    "plugin_path",
    "marketplace_path",
    "codex_config_path",
    "codex_plugin_cache_path",
    "codex_plugin_cache_invalidated_path",
)

def emit(state, root="", reason=""):
    for value in (state, str(root), reason):
        if "\n" in value or "\r" in value:
            raise SystemExit("Внутренняя ошибка: перенос строки в результате discovery")
        print(value)
    print(json.dumps(sorted({str(path) for path in state_protected}), ensure_ascii=False))

def refusal(reason, root=""):
    emit("REFUSED", root, reason)
    raise SystemExit(0)

def normalized(path):
    return Path(os.path.normpath(str(path)))

def overlaps(left, right):
    left = normalized(left)
    right = normalized(right)
    lexical_overlap = left == right or left in right.parents or right in left.parents
    real_left = normalized(Path(os.path.realpath(left)))
    real_right = normalized(Path(os.path.realpath(right)))
    real_overlap = real_left == real_right or real_left in real_right.parents or real_right in real_left.parents
    return lexical_overlap or real_overlap

def validate_protected_path(path, source):
    raw = str(path)
    if not path.is_absolute() or raw != os.path.normpath(raw):
        refusal(source + " содержит ненормализованный или не абсолютный protected path.")
    if any(ord(character) < 32 for character in raw):
        refusal(source + " содержит управляющие символы в protected path.")

for protected_path in protected:
    validate_protected_path(protected_path, "environment/default")

def validate_safe_root(root):
    raw = str(root)
    if not root.is_absolute() or raw != os.path.normpath(raw):
        refusal("install root не является нормализованным абсолютным путём.", root)
    if any(ord(character) < 32 for character in raw):
        refusal("install root содержит управляющие символы.", root)
    try:
        relative = root.relative_to(home)
    except ValueError:
        refusal("install root находится вне HOME.", root)
    if root == home or len(relative.parts) < 2 or root.name != "CodexTeamSkills":
        refusal("install root не проходит безопасные границы пути.", root)
    if any(overlaps(root, item) for item in protected):
        refusal("install root пересекается с защищённым артефактом.", root)
    cursor = home
    if os.path.lexists(cursor) and cursor.is_symlink():
        refusal("HOME является symlink; безопасная граница пути не доказана.", root)
    for part in relative.parts:
        cursor = cursor / part
        if os.path.lexists(cursor) and cursor.is_symlink():
            refusal("symlink в границе install root: " + str(cursor), root)

def validate_owned_tree(root):
    if not os.path.lexists(root):
        return set()
    mode = root.lstat().st_mode
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode) or os.path.ismount(root):
        refusal("install root является symlink/mount point или не является директорией.", root)

    top_entries = list(root.iterdir())
    top_level = {entry.name for entry in top_entries}
    unknown_top_level = sorted(top_level - allowed_root_names)
    if unknown_top_level:
        refusal("неизвестные объекты в updater root: " + ", ".join(unknown_top_level), root)
    for entry in top_entries:
        if entry.is_symlink() or not entry.is_dir() or os.path.ismount(entry):
            refusal("объект верхнего уровня не является обычной директорией: " + entry.name, root)

    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in directories + files:
            path = current_path / name
            if stat.S_ISLNK(path.lstat().st_mode):
                refusal("symlink внутри updater root: " + str(path.relative_to(root)), root)
            if path.is_dir() and os.path.ismount(path):
                refusal("mount point внутри updater root: " + str(path.relative_to(root)), root)
            if any(fnmatch.fnmatch(name, pattern) for pattern in recovery_patterns):
                refusal("recovery-копия внутри updater root: " + str(path.relative_to(root)), root)

    state_path = root / "state" / "state.json"
    if os.path.lexists(state_path):
        if state_path.is_symlink() or not state_path.is_file():
            refusal("state/state.json является symlink или не является обычным файлом.", root)
        try:
            state_payload = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception as exc:
            refusal("state/state.json не читается как JSON: " + type(exc).__name__ + ".", root)
        if not isinstance(state_payload, dict):
            refusal("state/state.json не содержит JSON object.", root)
        for key in state_path_keys:
            value = state_payload.get(key)
            if value in (None, ""):
                continue
            if not isinstance(value, str):
                refusal("known path key в state/state.json не является строкой: " + key + ".", root)
            path = Path(value)
            validate_protected_path(path, "state/state.json:" + key)
            state_protected.append(path)
        protected.extend(state_protected)
        if any(overlaps(root, item) for item in state_protected):
            refusal("updater root пересекается с protected path из state/state.json.", root)

    bin_path = root / "bin"
    if not bin_path.exists():
        return set()
    if not bin_path.is_dir() or bin_path.is_symlink():
        refusal("bin является symlink или не является директорией.", root)
    bin_names = {entry.name for entry in bin_path.iterdir()}
    unknown_bin = sorted(
        bin_names - allowed_bin_names - allowed_bin_directory_names
    )
    if unknown_bin:
        refusal("неизвестные объекты в bin: " + ", ".join(unknown_bin), root)
    for entry in bin_path.iterdir():
        if entry.name in allowed_bin_directory_names:
            if not entry.is_dir() or entry.is_symlink():
                refusal("__pycache__ не является обычной директорией.", root)
            for child in entry.iterdir():
                if (
                    not child.is_file()
                    or child.is_symlink()
                    or not allowed_registry_bytecode.fullmatch(child.name)
                ):
                    refusal(
                        "неизвестный объект в bin/__pycache__: " + child.name,
                        root,
                    )
            continue
        if not entry.is_file() or entry.is_symlink():
            refusal("объект в bin не является обычным файлом: " + entry.name, root)
    return bin_names & updater_markers

def parse_plist():
    if plist_path.is_symlink() or not plist_path.is_file():
        refusal("plist является symlink или не является обычным файлом.")
    try:
        with plist_path.open("rb") as handle:
            payload = plistlib.load(handle)
    except Exception as exc:
        refusal("plist не читается как корректный plist: " + type(exc).__name__ + ".")
    if not isinstance(payload, dict):
        refusal("plist не содержит словарь верхнего уровня.")
    allowed_keys = {
        "Label",
        "ProgramArguments",
        "StartInterval",
        "RunAtLoad",
        "StandardOutPath",
        "StandardErrorPath",
    }
    unknown_keys = sorted(set(payload) - allowed_keys)
    if unknown_keys:
        refusal("неизвестные ключи plist: " + ", ".join(unknown_keys) + ".")
    if payload.get("Label") != "com.codex-team-skills.autoupdate":
        refusal("Label в plist не совпадает с ожидаемым.")
    arguments = payload.get("ProgramArguments")
    if not isinstance(arguments, list) or len(arguments) != 2 or arguments[0] != "/bin/zsh":
        refusal("ProgramArguments в plist не совпадает с legacy-контрактом.")
    action_raw = arguments[1]
    if not isinstance(action_raw, str) or Path(action_raw).name not in scheduler_scripts:
        refusal("action в plist не является разрешённым updater-скриптом.")
    if payload.get("StandardOutPath") != stdout_log_raw or payload.get("StandardErrorPath") != stderr_log_raw:
        refusal("пути логов в plist не совпадают с legacy-контрактом.")
    if payload.get("StartInterval") not in (86400, 172800) or payload.get("RunAtLoad") is not False:
        refusal("режим запуска в plist не совпадает с legacy-контрактом.")
    action = Path(action_raw)
    if not action.is_absolute() or str(action) != os.path.normpath(str(action)):
        refusal("action в plist содержит небезопасный путь.")
    if action.parent.name != "bin":
        refusal("action в plist находится вне bin.")
    root = action.parent.parent
    validate_safe_root(root)
    markers = validate_owned_tree(root)
    if os.path.lexists(root) and not markers and not action.is_file():
        refusal("plist указывает на root без доказанных updater-маркеров.", root)
    if action.is_symlink():
        refusal("action в plist является symlink.", root)
    return root

if os.path.lexists(plist_path):
    emit("FOUND", parse_plist(), "LaunchAgent подтверждён точным plist.")
    raise SystemExit(0)

if service_loaded:
    refusal("LaunchAgent загружен, но точный plist отсутствует.")

validate_safe_root(canonical_root)
if not os.path.lexists(canonical_root):
    emit("NOT_FOUND", canonical_root, "LaunchAgent и canonical updater root отсутствуют.")
    raise SystemExit(0)

markers = validate_owned_tree(canonical_root)
required_fallback_markers = {"bootstrap-team-skills.sh", "update-team-skills.sh"}
if required_fallback_markers <= markers:
    emit("FOUND", canonical_root, "Canonical updater root подтверждён точными legacy-маркерами.")
elif markers:
    refusal("canonical root содержит неполный или неоднозначный набор updater-маркеров.", canonical_root)
else:
    emit("NOT_FOUND", "", "Canonical root не содержит updater-инфраструктуру.")
PY
}

DISCOVERY="$(run_discovery)" || unexpected "discovery завершился с ошибкой."

DISCOVERY_LINES=("${(@f)DISCOVERY}")
DISCOVERY_STATE="${DISCOVERY_LINES[1]:-}"
CANDIDATE_ROOT="${DISCOVERY_LINES[2]:-}"
DISCOVERY_REASON="${DISCOVERY_LINES[3]:-}"
DISCOVERY_STATE_PROTECTED_JSON="${DISCOVERY_LINES[4]:-[]}"
[[ -n "$DISCOVERY_STATE" ]] || unexpected "discovery не вернул состояние."

STATE_PROTECTED_OUTPUT="$(python3 - "$DISCOVERY_STATE_PROTECTED_JSON" <<'PY'
import json
import sys

paths = json.loads(sys.argv[1])
if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
    raise SystemExit("некорректный список protected paths")
for path in paths:
    print(path)
PY
)" || unexpected "discovery вернул некорректные protected paths."

PROTECTED_PATHS=(
  "$DEFAULT_PLUGIN_PATH"
  "$DEFAULT_MARKETPLACE_PATH"
  "$DEFAULT_CONFIG_PATH"
  "$DEFAULT_CACHE_PATH"
  "$PLUGIN_PATH"
  "$MARKETPLACE_PATH"
  "$CONFIG_PATH"
  "$CACHE_PATH"
)
if [[ -n "$STATE_PROTECTED_OUTPUT" ]]; then
  PROTECTED_PATHS+=("${(@f)STATE_PROTECTED_OUTPUT}")
fi

capture_protected BEFORE
SCHEDULER_BEFORE="$(scheduler_count)" || unexpected "не удалось проверить LaunchAgent."
ROOT_BEFORE="$(root_present "$CANDIDATE_ROOT")"
PROCESSES_BEFORE="$(updater_process_count "$CANDIDATE_ROOT")" || \
  unexpected "не удалось проверить updater-процессы."

render_report() {
  local outcome="$1"
  printf '\n[team-skills] %-22s | %-64s | %-64s\n' "Проверка" "Before" "After"
  printf '[team-skills] %s\n' "-----------------------+------------------------------------------------------------------+------------------------------------------------------------------"
  printf '[team-skills] %-22s | %-64s | %-64s\n' "Scheduler/LaunchAgent" "$SCHEDULER_BEFORE" "$SCHEDULER_AFTER"
  printf '[team-skills] %-22s | %-64s | %-64s\n' "Updater processes" "$PROCESSES_BEFORE" "$PROCESSES_AFTER"
  printf '[team-skills] %-22s | %-64s | %-64s\n' "Updater root" "$ROOT_BEFORE" "$ROOT_AFTER"
  printf '[team-skills] %-22s | %-64s | %-64s\n' "Plugin SHA-256" "$BEFORE_PLUGIN" "$AFTER_PLUGIN"
  printf '[team-skills] %-22s | %-64s | %-64s\n' "Marketplace SHA-256" "$BEFORE_MARKETPLACE" "$AFTER_MARKETPLACE"
  printf '[team-skills] %-22s | %-64s | %-64s\n' "Config SHA-256" "$BEFORE_CONFIG" "$AFTER_CONFIG"
  printf '[team-skills] %-22s | %-64s | %-64s\n' "Active cache SHA-256" "$BEFORE_CACHE" "$AFTER_CACHE"
  printf '[team-skills] %-22s | %-64s | %-64s\n' "Protected set SHA-256" "$BEFORE_PROTECTED_SET" "$AFTER_PROTECTED_SET"
  info "Результат: $outcome"
}

capture_after() {
  capture_protected AFTER
  SCHEDULER_AFTER="$(scheduler_count)" || SCHEDULER_AFTER="ERROR"
  ROOT_AFTER="$(root_present "$CANDIDATE_ROOT")"
  PROCESSES_AFTER="$(updater_process_count "$CANDIDATE_ROOT")" || PROCESSES_AFTER="ERROR"
}

protected_unchanged() {
  [[ "$BEFORE_PLUGIN" == "$AFTER_PLUGIN" && \
     "$BEFORE_MARKETPLACE" == "$AFTER_MARKETPLACE" && \
     "$BEFORE_CONFIG" == "$AFTER_CONFIG" && \
     "$BEFORE_CACHE" == "$AFTER_CACHE" && \
     "$BEFORE_PROTECTED_SET" == "$AFTER_PROTECTED_SET" ]]
}

if [[ "$DISCOVERY_STATE" == "REFUSED" ]]; then
  info "Очистка запрещена: $DISCOVERY_REASON"
  capture_after
  render_report "REFUSED_UNSAFE"
  exit 3
fi

if [[ "$DISCOVERY_STATE" == "NOT_FOUND" ]]; then
  info "$DISCOVERY_REASON"
  capture_after
  render_report "NOT_FOUND"
  exit 0
fi

if [[ "$DISCOVERY_STATE" != "FOUND" ]]; then
  unexpected "неизвестное состояние discovery: $DISCOVERY_STATE."
fi

info "$DISCOVERY_REASON"
info "LaunchAgent: $PLIST_PATH"
info "Updater root: $CANDIDATE_ROOT"
info "Логи: $STDOUT_LOG; $STDERR_LOG"
info "Активный plugin: $PLUGIN_PATH"
info "Активный marketplace: $MARKETPLACE_PATH"
info "Активный config: $CONFIG_PATH"
info "Активный cache: $CACHE_PATH"

if [[ "$MODE" == "dry-run" ]]; then
  capture_after
  if ! protected_unchanged; then
    render_report "INCOMPLETE"
    exit 4
  fi
  render_report "DRY_RUN_SAFE"
  exit 0
fi

if service_is_loaded; then
  launchctl bootout "$SERVICE_TARGET" >/dev/null 2>&1 || \
    launchctl bootout "gui/$UID" "$PLIST_PATH" >/dev/null 2>&1 || true
  if service_is_loaded; then
    capture_after
    render_report "INCOMPLETE"
    info "Не удалось остановить точный LaunchAgent; файлы не удалены."
    exit 4
  fi
fi

wait_for_no_processes() {
  local attempts="$1"
  local delay="$2"
  local count
  local attempt=0
  while (( attempt < attempts )); do
    count="$(updater_process_count "$CANDIDATE_ROOT")" || return 1
    [[ "$count" == "0" ]] && return 0
    sleep "$delay"
    (( attempt += 1 ))
  done
  return 1
}

wait_for_no_processes 100 0.1 || true

PIDS="$(list_updater_pids "$CANDIDATE_ROOT")" || {
  capture_after
  render_report "INCOMPLETE"
  info "Не удалось повторно проверить updater-процессы; файлы не удалены."
  exit 4
}
if [[ -n "$PIDS" ]]; then
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    CURRENT_PIDS="$(list_updater_pids "$CANDIDATE_ROOT")" || {
      capture_after
      render_report "INCOMPLETE"
      info "Не удалось подтвердить PID перед TERM; файлы не удалены."
      exit 4
    }
    if printf '%s\n' "$CURRENT_PIDS" | awk -v expected="$pid" '$0 == expected {found = 1} END {exit !found}'; then
      kill -TERM "$pid" >/dev/null 2>&1 || true
    fi
  done <<< "$PIDS"
fi

wait_for_no_processes 50 0.1 || true

PIDS="$(list_updater_pids "$CANDIDATE_ROOT")" || {
  capture_after
  render_report "INCOMPLETE"
  info "Не удалось повторно проверить updater-процессы; файлы не удалены."
  exit 4
}
if [[ -n "$PIDS" ]]; then
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    CURRENT_PIDS="$(list_updater_pids "$CANDIDATE_ROOT")" || {
      capture_after
      render_report "INCOMPLETE"
      info "Не удалось подтвердить PID перед KILL; файлы не удалены."
      exit 4
    }
    if printf '%s\n' "$CURRENT_PIDS" | awk -v expected="$pid" '$0 == expected {found = 1} END {exit !found}'; then
      kill -KILL "$pid" >/dev/null 2>&1 || true
    fi
  done <<< "$PIDS"
fi

if ! wait_for_no_processes 20 0.1; then
  capture_after
  render_report "INCOMPLETE"
  info "Не удалось остановить все точные updater-процессы; файлы не удалены."
  exit 4
fi

LOADED=0
service_is_loaded && LOADED=1
RECHECK="$(run_discovery)" || {
  capture_after
  render_report "INCOMPLETE"
  info "Повторный preflight завершился ошибкой; файлы не удалены."
  exit 4
}
RECHECK_LINES=("${(@f)RECHECK}")
RECHECK_STATE="${RECHECK_LINES[1]:-}"
RECHECK_ROOT="${RECHECK_LINES[2]:-}"
RECHECK_STATE_PROTECTED_JSON="${RECHECK_LINES[4]:-[]}"
if [[ "$RECHECK_STATE" != "FOUND" || "$RECHECK_ROOT" != "$CANDIDATE_ROOT" || \
      "$RECHECK_STATE_PROTECTED_JSON" != "$DISCOVERY_STATE_PROTECTED_JSON" ]]; then
  capture_after
  render_report "INCOMPLETE"
  info "Scope изменился после остановки процессов; файлы не удалены."
  exit 4
fi

DELETE_FAILED=0
if [[ -e "$PLIST_PATH" || -L "$PLIST_PATH" ]]; then
  rm -f "$PLIST_PATH" || DELETE_FAILED=1
fi
if [[ -e "$STDOUT_LOG" || -L "$STDOUT_LOG" ]]; then
  rm -f "$STDOUT_LOG" || DELETE_FAILED=1
fi
if [[ -e "$STDERR_LOG" || -L "$STDERR_LOG" ]]; then
  rm -f "$STDERR_LOG" || DELETE_FAILED=1
fi
if [[ -n "$CANDIDATE_ROOT" && ( -e "$CANDIDATE_ROOT" || -L "$CANDIDATE_ROOT" ) ]]; then
  rm -rf "$CANDIDATE_ROOT" || DELETE_FAILED=1
fi

capture_after
if (( DELETE_FAILED )) || [[ "$SCHEDULER_AFTER" != "0" || "$PROCESSES_AFTER" != "0" || "$ROOT_AFTER" != "false" ]] || \
   ! protected_unchanged; then
  render_report "INCOMPLETE"
  info "Очистка началась, но доказанные postcondition не достигнуты."
  exit 4
fi

render_report "CLEANED"
exit 0
