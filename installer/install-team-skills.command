#!/usr/bin/env zsh
set -euo pipefail

PLUGIN_NAME="team-skills"
MARKETPLACE_NAME="codex-team-skills"
BAKED_RELEASE_TAG="__TEAM_SKILLS_RELEASE_TAG__"
MANIFEST_URL="${CODEX_TEAM_SKILLS_MANIFEST_URL:-}"
PLUGIN_DEST="${CODEX_TEAM_SKILLS_PLUGIN_DIR:-$HOME/plugins/team-skills}"
MARKETPLACE_ROOT="${CODEX_TEAM_SKILLS_MARKETPLACE_ROOT:-$HOME}"
MARKETPLACE_PATH="${CODEX_TEAM_SKILLS_MARKETPLACE:-$MARKETPLACE_ROOT/.agents/plugins/marketplace.json}"
CODEX_CONFIG_PATH="${CODEX_TEAM_SKILLS_CODEX_CONFIG:-$HOME/.codex/config.toml}"
CODEX_PLUGIN_CACHE_DIR="${CODEX_TEAM_SKILLS_CODEX_PLUGIN_CACHE_DIR:-$HOME/.codex/plugins/cache/$MARKETPLACE_NAME}"
VALIDATE_ONLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --manifest-url)
      [[ $# -ge 2 && -n "$2" ]] || {
        printf '[team-skills] Для --manifest-url нужен URL.\n' >&2
        exit 2
      }
      MANIFEST_URL="$2"
      shift 2
      ;;
    --validate-only)
      VALIDATE_ONLY=1
      shift
      ;;
    *)
      printf '[team-skills] Неизвестный аргумент: %s\n' "$1" >&2
      exit 2
      ;;
  esac
done

info() {
  printf '[team-skills] %s\n' "$1"
}

fail() {
  info "$1" >&2
  exit 1
}

if [[ "$VALIDATE_ONLY" == "1" ]]; then
  info "ValidateOnly: install-team-skills.command разобран без выполнения установки."
  exit 0
fi

if [[ -z "$MANIFEST_URL" ]]; then
  [[ "$BAKED_RELEASE_TAG" != __TEAM_SKILLS_* ]] || \
    fail "Запущен исходный installer без release tag. Используйте release-asset."
  MANIFEST_URL="https://github.com/kir-kopylov/codex-team-skills/releases/download/$BAKED_RELEASE_TAG/manifest.json"
fi

for command_name in curl python3 unzip; do
  command -v "$command_name" >/dev/null 2>&1 || fail "Для установки нужен $command_name."
done
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' || \
  fail "Для установки нужен Python 3.11 или новее."

EXPECTED_RELEASE_TAG="$(python3 - "$MANIFEST_URL" <<'PY'
import re
import sys
from urllib.parse import urlparse

url = urlparse(sys.argv[1])
match = re.fullmatch(
    r"/kir-kopylov/codex-team-skills/releases/download/"
    r"(?P<tag>team-skills-v[A-Za-z0-9._-]+)/manifest\.json",
    url.path,
)
if (
    url.scheme != "https"
    or url.hostname != "github.com"
    or url.port not in (None, 443)
    or url.username is not None
    or url.password is not None
    or url.params
    or url.query
    or url.fragment
    or match is None
):
    raise SystemExit("ManifestUrl должен быть immutable HTTPS URL официального GitHub release")
print(match.group("tag"))
PY
)" || fail "ManifestUrl должен указывать на manifest.json конкретного GitHub release."
if [[ "$BAKED_RELEASE_TAG" != __TEAM_SKILLS_* && "$EXPECTED_RELEASE_TAG" != "$BAKED_RELEASE_TAG" ]]; then
  fail "ManifestUrl не совпадает с release tag, встроенным в installer."
fi
RELEASE_BASE="https://github.com/kir-kopylov/codex-team-skills/releases/download/$EXPECTED_RELEASE_TAG"

assert_safe_managed_path() {
  local target_path="$1"
  local expected_leaf="$2"
  local label="$3"
  local resolved="${target_path:A}"
  local home_resolved="${HOME:A}"
  [[ -n "$resolved" && "$resolved" != "/" && "$resolved" != "$home_resolved" ]] || \
    fail "Небезопасный путь $label: $target_path"
  [[ "${resolved:t}" == "$expected_leaf" ]] || \
    fail "Небезопасный путь $label: $target_path"
  [[ ! -L "$target_path" ]] || fail "$label не должен быть symlink: $target_path"
}

assert_safe_managed_path "$PLUGIN_DEST" "$PLUGIN_NAME" "plugin destination"
assert_safe_managed_path "$CODEX_PLUGIN_CACHE_DIR" "$MARKETPLACE_NAME" "Codex plugin cache"
[[ ! -e "$PLUGIN_DEST" || -d "$PLUGIN_DEST" ]] || \
  fail "Plugin destination должен быть каталогом: $PLUGIN_DEST"
[[ ! -e "$CODEX_PLUGIN_CACHE_DIR" || -d "$CODEX_PLUGIN_CACHE_DIR" ]] || \
  fail "Codex plugin cache должен быть каталогом: $CODEX_PLUGIN_CACHE_DIR"
PLUGIN_DEST="${PLUGIN_DEST:A}"
MARKETPLACE_ROOT="${MARKETPLACE_ROOT:A}"
MARKETPLACE_PATH="${MARKETPLACE_PATH:A}"
CODEX_CONFIG_PATH="${CODEX_CONFIG_PATH:A}"
CODEX_PLUGIN_CACHE_DIR="${CODEX_PLUGIN_CACHE_DIR:A}"

download_file() {
  local url="$1"
  local destination="$2"
  rm -f -- "$destination"
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

file_sha256() {
  python3 - "$1" <<'PY'
import hashlib
import sys
from pathlib import Path

print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest())
PY
}

verify_sha256() {
  local actual
  actual="$(file_sha256 "$1")"
  [[ "$actual" == "${2:l}" ]] || fail "SHA-256 файла ${1:t} не совпадает с manifest."
}

verify_file_size() {
  local actual
  actual="$(LC_ALL=C wc -c < "$1" | tr -d '[:space:]')"
  [[ "$actual" == "$2" ]] || \
    fail "Размер файла ${1:t} не совпадает с manifest: ожидалось $2, получено $actual."
}

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/codex-team-skills-install.XXXXXX")"
TRANSACTION_ACTIVE=0
HAD_PLUGIN=0
PLUGIN_MOVED_ASIDE=0
PLUGIN_ACTIVATED=0
MARKETPLACE_EXISTED=0
CONFIG_EXISTED=0
STAGED_PLUGIN=""
PREVIOUS_PLUGIN=""
MARKETPLACE_SNAPSHOT="$WORK_DIR/marketplace.original"
CONFIG_SNAPSHOT="$WORK_DIR/config.original"

restore_optional_file() {
  local target="$1"
  local snapshot="$2"
  local existed="$3"
  if [[ "$existed" == "1" ]]; then
    mkdir -p -- "${target:h}" || return 1
    local temporary="$target.rollback.$$.$RANDOM"
    cp -p -- "$snapshot" "$temporary" || return 1
    mv -f -- "$temporary" "$target" || return 1
  else
    rm -f -- "$target" || return 1
  fi
}

rollback_transaction() {
  local rollback_failed=0
  if [[ "$PLUGIN_ACTIVATED" == "1" ]]; then
    rm -rf -- "$PLUGIN_DEST" || rollback_failed=1
  fi
  if [[ "$PLUGIN_MOVED_ASIDE" == "1" && -e "$PREVIOUS_PLUGIN" ]]; then
    mv -- "$PREVIOUS_PLUGIN" "$PLUGIN_DEST" || rollback_failed=1
  fi
  restore_optional_file "$MARKETPLACE_PATH" "$MARKETPLACE_SNAPSHOT" "$MARKETPLACE_EXISTED" || rollback_failed=1
  restore_optional_file "$CODEX_CONFIG_PATH" "$CONFIG_SNAPSHOT" "$CONFIG_EXISTED" || rollback_failed=1
  [[ "$rollback_failed" == "0" ]]
}

on_exit() {
  local exit_code=$?
  trap - EXIT
  if [[ "$TRANSACTION_ACTIVE" == "1" ]]; then
    rollback_transaction || exit_code=1
  fi
  rm -rf -- "$WORK_DIR"
  exit "$exit_code"
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

MANIFEST_FILE="$WORK_DIR/manifest.json"
BUNDLE_FILE="$WORK_DIR/team-skills-bundle.zip"
EXPANDED_DIR="$WORK_DIR/expanded"
mkdir -p -- "$EXPANDED_DIR"

info "Скачиваю manifest конкретного GitHub release."
download_file "$MANIFEST_URL" "$MANIFEST_FILE" || fail "Не удалось скачать manifest после повторных попыток."

MANIFEST_VALUES="$(python3 - "$MANIFEST_FILE" "$EXPECTED_RELEASE_TAG" "$RELEASE_BASE" <<'PY'
import json
import re
import sys
from pathlib import Path

path, expected_tag, release_base = sys.argv[1:]
try:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
except Exception as exc:
    raise SystemExit(f"Manifest JSON невалиден: {exc}")

expected_keys = {
    "schema_version",
    "release_tag",
    "commit",
    "plugin_version",
    "bundle",
}
if set(manifest) != expected_keys or manifest.get("schema_version") != 1:
    raise SystemExit("Manifest не соответствует минимальной schema_version=1")
if manifest.get("release_tag") != expected_tag:
    raise SystemExit("release_tag в manifest не совпадает с installer")
if not re.fullmatch(r"[0-9a-fA-F]{7,64}", str(manifest.get("commit", ""))):
    raise SystemExit("commit в manifest некорректен")
if not isinstance(manifest.get("plugin_version"), str) or not manifest["plugin_version"]:
    raise SystemExit("plugin_version в manifest некорректен")

bundle = manifest.get("bundle")
if not isinstance(bundle, dict) or set(bundle) != {"url", "size", "sha256"}:
    raise SystemExit("метаданные plugin bundle некорректны")
if bundle.get("url") != f"{release_base}/team-skills-bundle.zip":
    raise SystemExit("bundle URL должен указывать на тот же immutable GitHub release")
if not isinstance(bundle.get("size"), int) or bundle["size"] <= 0:
    raise SystemExit("размер plugin bundle некорректен")
if not re.fullmatch(r"[0-9a-fA-F]{64}", str(bundle.get("sha256", ""))):
    raise SystemExit("SHA-256 plugin bundle некорректен")

print("\t".join([
    manifest["release_tag"],
    manifest["commit"],
    manifest["plugin_version"],
    bundle["url"],
    str(bundle["size"]),
    bundle["sha256"].lower(),
]))
PY
)" || fail "Manifest не прошёл проверку."
IFS=$'\t' read -r RELEASE_TAG COMMIT PLUGIN_VERSION BUNDLE_URL BUNDLE_SIZE BUNDLE_SHA <<< "$MANIFEST_VALUES"

info "Скачиваю plugin bundle."
download_file "$BUNDLE_URL" "$BUNDLE_FILE" || fail "Не удалось скачать plugin bundle после повторных попыток."
verify_file_size "$BUNDLE_FILE" "$BUNDLE_SIZE"
verify_sha256 "$BUNDLE_FILE" "$BUNDLE_SHA"
unzip -q "$BUNDLE_FILE" -d "$EXPANDED_DIR" || fail "Не удалось распаковать plugin bundle."

PLUGIN_ROOT="$EXPANDED_DIR/team-skills"
python3 - "$PLUGIN_ROOT/.codex-plugin/plugin.json" "$PLUGIN_NAME" "$PLUGIN_VERSION" "$RELEASE_TAG" "$COMMIT" <<'PY' || \
  fail "Идентичность plugin в bundle не совпадает с manifest."
import json
import sys
from pathlib import Path

path, expected_name, expected_version, expected_tag, expected_commit = sys.argv[1:]
try:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
except Exception as exc:
    raise SystemExit(f"manifest plugin невалиден: {exc}")
if (
    manifest.get("name") != expected_name
    or manifest.get("version") != expected_version
    or manifest.get("release_tag") != expected_tag
    or manifest.get("commit") != expected_commit
    or manifest.get("skills") != "./skills/"
):
    raise SystemExit("идентичность plugin не совпадает")
PY

if [[ -e "$MARKETPLACE_PATH" || -L "$MARKETPLACE_PATH" ]]; then
  [[ -f "$MARKETPLACE_PATH" && ! -L "$MARKETPLACE_PATH" ]] || \
    fail "Marketplace path должен быть обычным файлом: $MARKETPLACE_PATH"
  cp -p -- "$MARKETPLACE_PATH" "$MARKETPLACE_SNAPSHOT"
  MARKETPLACE_EXISTED=1
fi
if [[ -e "$CODEX_CONFIG_PATH" || -L "$CODEX_CONFIG_PATH" ]]; then
  [[ -f "$CODEX_CONFIG_PATH" && ! -L "$CODEX_CONFIG_PATH" ]] || \
    fail "Codex config path должен быть обычным файлом: $CODEX_CONFIG_PATH"
  cp -p -- "$CODEX_CONFIG_PATH" "$CONFIG_SNAPSHOT"
  CONFIG_EXISTED=1
fi

MARKETPLACE_NEXT="$WORK_DIR/marketplace.next"
CONFIG_NEXT="$WORK_DIR/config.next"
python3 - \
  "$MARKETPLACE_SNAPSHOT" "$MARKETPLACE_EXISTED" "$MARKETPLACE_NEXT" \
  "$CONFIG_SNAPSHOT" "$CONFIG_EXISTED" "$CONFIG_NEXT" \
  "$PLUGIN_NAME" "$PLUGIN_DEST" "$MARKETPLACE_ROOT" <<'PY' || \
  fail "Marketplace или Codex config не прошли безопасную подготовку."
import json
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

(
    marketplace_snapshot,
    marketplace_existed,
    marketplace_next,
    config_snapshot,
    config_existed,
    config_next,
    plugin_name,
    plugin_dest,
    marketplace_root,
) = sys.argv[1:]

if marketplace_existed == "1":
    data = json.loads(Path(marketplace_snapshot).read_text(encoding="utf-8-sig"))
else:
    data = {
        "name": "local-team-skills",
        "interface": {"displayName": "Локальные командные skills"},
        "plugins": [],
    }
if not isinstance(data, dict):
    raise SystemExit("Marketplace JSON должен содержать объект верхнего уровня")
plugins = data.setdefault("plugins", [])
if not isinstance(plugins, list):
    raise SystemExit("Marketplace plugins должен быть списком")
data.setdefault("interface", {"displayName": "Локальные командные skills"})
data["plugins"] = [
    entry
    for entry in plugins
    if not (isinstance(entry, dict) and entry.get("name") == plugin_name)
]
data["plugins"].append({
    "name": plugin_name,
    "source": {"source": "local", "path": plugin_dest.replace("\\", "/")},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    "category": "Productivity",
})
Path(marketplace_next).write_text(
    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

BEGIN = "# BEGIN codex-team-skills managed block"
END = "# END codex-team-skills managed block"
TARGETS = {
    "[marketplaces.codex-team-skills]",
    '[plugins."team-skills@codex-team-skills"]',
}

def strip_managed_content(text: str) -> str:
    lines = text.splitlines()
    kept: list[str] = []
    rescued: list[str] = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped == BEGIN:
            index += 1
            while index < len(lines) and lines[index].strip() != END:
                header = lines[index].strip()
                if header.startswith("[") and header not in TARGETS:
                    rescued.append(lines[index])
                    index += 1
                    while (
                        index < len(lines)
                        and lines[index].strip() != END
                        and not lines[index].lstrip().startswith("[")
                    ):
                        rescued.append(lines[index])
                        index += 1
                else:
                    index += 1
            if index < len(lines):
                index += 1
            continue
        if stripped in TARGETS:
            index += 1
            while index < len(lines) and not lines[index].lstrip().startswith("["):
                index += 1
            continue
        kept.append(lines[index])
        index += 1
    while rescued and not rescued[-1].strip():
        rescued.pop()
    if rescued:
        if kept and kept[-1].strip():
            kept.append("")
        kept.extend(rescued)
    return "\n".join(kept).rstrip() + "\n"

config_text = (
    Path(config_snapshot).read_text(encoding="utf-8-sig")
    if config_existed == "1"
    else ""
)
next_config = strip_managed_content(config_text)
if next_config.strip():
    next_config = next_config.rstrip() + "\n\n"
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
source = json.dumps(marketplace_root, ensure_ascii=False)
next_config += (
    f"{BEGIN}\n"
    "[marketplaces.codex-team-skills]\n"
    f'last_updated = "{now}"\n'
    'source_type = "local"\n'
    f"source = {source}\n"
    "\n"
    '[plugins."team-skills@codex-team-skills"]\n'
    "enabled = true\n"
    f"{END}\n"
)
tomllib.loads(next_config or "\n")
Path(config_next).write_text(next_config, encoding="utf-8")
PY

write_prepared_file() {
  local prepared="$1"
  local target="$2"
  local temporary="$target.tmp.$$.$RANDOM"
  mkdir -p -- "${target:h}" || return 1
  cp -- "$prepared" "$temporary" || return 1
  mv -f -- "$temporary" "$target" || return 1
}

STAGED_PLUGIN="$PLUGIN_DEST.tmp.$$.$RANDOM"
PREVIOUS_PLUGIN="$PLUGIN_DEST.previous.$$.$RANDOM"
mkdir -p -- "${PLUGIN_DEST:h}"
cp -R -- "$PLUGIN_ROOT" "$STAGED_PLUGIN" || fail "Не удалось подготовить plugin к установке."

TRANSACTION_ERROR=""
run_transaction() {
  TRANSACTION_ACTIVE=1
  if [[ -e "$PLUGIN_DEST" ]]; then
    HAD_PLUGIN=1
    mv -- "$PLUGIN_DEST" "$PREVIOUS_PLUGIN" || {
      TRANSACTION_ERROR="не удалось убрать прежний plugin"
      return 1
    }
    PLUGIN_MOVED_ASIDE=1
  fi
  mv -- "$STAGED_PLUGIN" "$PLUGIN_DEST" || {
    TRANSACTION_ERROR="не удалось активировать новый plugin"
    return 1
  }
  PLUGIN_ACTIVATED=1
  write_prepared_file "$MARKETPLACE_NEXT" "$MARKETPLACE_PATH" || {
    TRANSACTION_ERROR="не удалось обновить marketplace"
    return 1
  }
  write_prepared_file "$CONFIG_NEXT" "$CODEX_CONFIG_PATH" || {
    TRANSACTION_ERROR="не удалось обновить Codex config"
    return 1
  }
  [[ -f "$PLUGIN_DEST/.codex-plugin/plugin.json" ]] || {
    TRANSACTION_ERROR="установленный plugin не прошёл post-check"
    return 1
  }
  if [[ -e "$CODEX_PLUGIN_CACHE_DIR" ]]; then
    rm -rf -- "$CODEX_PLUGIN_CACHE_DIR" || {
      TRANSACTION_ERROR="не удалось удалить точный Codex plugin cache"
      return 1
    }
  fi
  if [[ "$HAD_PLUGIN" == "1" && -e "$PREVIOUS_PLUGIN" ]]; then
    rm -rf -- "$PREVIOUS_PLUGIN" || {
      TRANSACTION_ERROR="не удалось удалить временную recovery-копию прежнего plugin"
      return 1
    }
  fi
  TRANSACTION_ACTIVE=0
}

if ! run_transaction; then
  if rollback_transaction; then
    TRANSACTION_ACTIVE=0
    fail "Установка не завершена; прежний plugin и registry восстановлены: $TRANSACTION_ERROR."
  fi
  TRANSACTION_ACTIVE=0
  fail "Установка не завершена, а полный rollback не подтверждён: $TRANSACTION_ERROR."
fi

info "Установлена версия team-skills $PLUGIN_VERSION из release $RELEASE_TAG."
info "Автообновления нет: для новой версии вручную запустите новый installer."
info "Перезапустите Codex, чтобы он перечитал plugin."
