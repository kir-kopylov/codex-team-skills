#!/usr/bin/env zsh
set -euo pipefail

UPDATER_VERSION="1.0.0"
PLUGIN_NAME="team-skills"
MARKETPLACE_NAME="codex-team-skills"
RELEASE_BASE="https://github.com/kir-kopylov/codex-team-skills/releases/latest/download"
LATEST_URL="${CODEX_TEAM_SKILLS_LATEST_URL:-$RELEASE_BASE/latest.json}"
MANIFEST_URL="${CODEX_TEAM_SKILLS_MANIFEST_URL:-}"
INSTALL_ROOT="${CODEX_TEAM_SKILLS_HOME:-$HOME/Library/Application Support/CodexTeamSkills}"
BIN_DIR="$INSTALL_ROOT/bin"
CACHE_DIR="$INSTALL_ROOT/cache"
STATE_DIR="$INSTALL_ROOT/state"
LOG_DIR="$INSTALL_ROOT/logs"
PLUGIN_DEST="${CODEX_TEAM_SKILLS_PLUGIN_DIR:-$HOME/plugins/team-skills}"
MARKETPLACE_ROOT="${CODEX_TEAM_SKILLS_MARKETPLACE_ROOT:-$HOME}"
MARKETPLACE_PATH="${CODEX_TEAM_SKILLS_MARKETPLACE:-$MARKETPLACE_ROOT/.agents/plugins/marketplace.json}"
CODEX_CONFIG_PATH="${CODEX_TEAM_SKILLS_CODEX_CONFIG:-$HOME/.codex/config.toml}"
CODEX_PLUGIN_CACHE_DIR="${CODEX_TEAM_SKILLS_CODEX_PLUGIN_CACHE_DIR:-$HOME/.codex/plugins/cache/$MARKETPLACE_NAME}"
PUBLIC_KEY_PATH="${CODEX_TEAM_SKILLS_PUBLIC_KEY:-$BIN_DIR/team-skills-public-key.pem}"
# Trust anchor pinned at build time: sha256 of installer/team-skills-public-key.pem.
# Если установленный public key не совпадает с этим значением — это подмена якоря доверия.
EXPECTED_PUBLIC_KEY_SHA256="6303efaa119fef81c5c40a281e85998351aa5c7a81100e00e4921198403371a6"
REGISTRY_HELPER="${CODEX_TEAM_SKILLS_REGISTRY_HELPER:-$BIN_DIR/team-skills-registry.py}"
STATE_PATH="$STATE_DIR/state.json"
LOG_PATH="$LOG_DIR/team-skills-update.log"
ALLOW_UNSIGNED="${CODEX_TEAM_SKILLS_ALLOW_UNSIGNED:-0}"
MODE="update"
INVALIDATED_CODEX_PLUGIN_CACHE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repair-install|--repair)
      MODE="repair"
      shift
      ;;
    --manifest-url)
      MANIFEST_URL="${2:-}"
      shift 2
      ;;
    --latest-url)
      LATEST_URL="${2:-}"
      shift 2
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

log() {
  mkdir -p "$LOG_DIR"
  printf '%s %s\n' "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "$1" >> "$LOG_PATH"
  info "$1"
}

require_python3() {
  if ! command -v python3 >/dev/null 2>&1; then
    log "Обновление не применено: нужен python3 для проверки manifest, marketplace и registry."
    exit 1
  fi
}

file_sha256() {
  local file_path="$1"
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$file_path" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$file_path" | awk '{print $1}'
  elif command -v openssl >/dev/null 2>&1; then
    openssl dgst -sha256 "$file_path" | awk '{print $NF}'
  else
    return 1
  fi
}

verify_public_key_pin() {
  if [[ ! -f "$PUBLIC_KEY_PATH" ]]; then
    log "Обновление не применено: public key не найден: $PUBLIC_KEY_PATH"
    exit 1
  fi
  local actual
  if ! actual="$(file_sha256 "$PUBLIC_KEY_PATH")"; then
    log "Обновление не применено: нет shasum/sha256sum/openssl для проверки public key."
    exit 1
  fi
  actual="$(printf '%s' "$actual" | tr '[:upper:]' '[:lower:]')"
  if [[ "$actual" != "$EXPECTED_PUBLIC_KEY_SHA256" ]]; then
    log "Обновление не применено: public key не совпадает с закреплённым якорем доверия (sha256 mismatch). Возможна подмена ключа подписи. Оставляю текущий рабочий plugin без изменений."
    exit 1
  fi
}

verify_signature() {
  local payload="$1"
  local signature="$2"
  if [[ "$ALLOW_UNSIGNED" == "1" ]]; then
    log "ВНИМАНИЕ: проверка подписи ОТКЛЮЧЕНА (CODEX_TEAM_SKILLS_ALLOW_UNSIGNED=1). Это небезопасный режим только для разработки: устанавливается НЕпроверенный код. В обычной работе не используйте."
    return 0
  fi
  verify_public_key_pin
  if ! command -v openssl >/dev/null 2>&1; then
    log "Обновление не применено: нужен openssl для проверки подписи."
    exit 1
  fi
  openssl dgst -sha256 -verify "$PUBLIC_KEY_PATH" -signature "$signature" "$payload" >/dev/null
}

download_signed() {
  local url="$1"
  local dest="$2"
  curl -fsSL "$url" -o "$dest"
  if [[ "$ALLOW_UNSIGNED" == "1" ]]; then
    return 0
  fi
  curl -fsSL "$url.sig" -o "$dest.sig"
  verify_signature "$dest" "$dest.sig"
}

verify_sha256() {
  local file_path="$1"
  local expected="$2"
  local actual
  actual="$(python3 - "$file_path" <<'PY'
import hashlib
import sys
from pathlib import Path

print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest())
PY
)"
  expected="$(printf '%s' "$expected" | tr '[:upper:]' '[:lower:]')"
  if [[ "$actual" != "$expected" ]]; then
    log "Обновление не применено: checksum mismatch для $file_path."
    exit 1
  fi
}

update_marketplace() {
  python3 - "$MARKETPLACE_PATH" "$PLUGIN_NAME" "$PLUGIN_DEST" <<'PY'
import json
import sys
from pathlib import Path

marketplace_path = Path(sys.argv[1]).expanduser()
plugin_name = sys.argv[2]
plugin_dest = Path(sys.argv[3]).expanduser()
marketplace_path.parent.mkdir(parents=True, exist_ok=True)

if marketplace_path.exists():
    data = json.loads(marketplace_path.read_text(encoding="utf-8"))
else:
    data = {
        "name": "local-team-skills",
        "interface": {"displayName": "Локальные командные skills"},
        "plugins": [],
    }

data.setdefault("name", "local-team-skills")
data.setdefault("interface", {}).setdefault("displayName", "Локальные командные skills")
plugins = [entry for entry in data.setdefault("plugins", []) if entry.get("name") != plugin_name]
plugins.append({
    "name": plugin_name,
    "source": {"source": "local", "path": str(plugin_dest).replace("\\", "/")},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    "category": "Productivity",
})
data["plugins"] = plugins
marketplace_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

update_codex_registry() {
  if [[ ! -f "$REGISTRY_HELPER" ]]; then
    log "Обновление не применено: registry helper не найден: $REGISTRY_HELPER"
    exit 1
  fi
  python3 "$REGISTRY_HELPER" ensure \
    --config "$CODEX_CONFIG_PATH" \
    --marketplace-root "$MARKETPLACE_ROOT" >/dev/null
}

invalidate_codex_plugin_cache() {
  local cache_dir="$CODEX_PLUGIN_CACHE_DIR"
  if [[ -z "$cache_dir" || "$cache_dir" == "/" || "$cache_dir" == "$HOME" || "$cache_dir" == "$HOME/" ]]; then
    log "Codex plugin cache invalidation skipped: unsafe cache path: $cache_dir"
    return 0
  fi

  if [[ ! -d "$cache_dir" ]]; then
    log "Codex plugin cache already absent: $cache_dir"
    return 0
  fi

  local stamp stale_dir
  stamp="$(date -u +"%Y%m%dT%H%M%SZ")"
  stale_dir="$cache_dir.stale.$stamp.$$"
  if mv "$cache_dir" "$stale_dir"; then
    INVALIDATED_CODEX_PLUGIN_CACHE="$stale_dir"
    log "Codex plugin cache invalidated: moved $cache_dir -> $stale_dir"
    return 0
  fi

  rm -rf "$cache_dir"
  INVALIDATED_CODEX_PLUGIN_CACHE="$cache_dir"
  log "Codex plugin cache invalidated: removed $cache_dir"
}

find_plugin_root() {
  local expanded="$1"
  for candidate in "$expanded/team-skills" "$expanded/plugins/team-skills" "$expanded"; do
    if [[ -f "$candidate/.codex-plugin/plugin.json" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

swap_plugin() {
  local source_dir="$1"
  local tmp_dest="$PLUGIN_DEST.tmp.$$"
  local backup_dest="$PLUGIN_DEST.previous"

  mkdir -p "$(dirname "$PLUGIN_DEST")"
  rm -rf "$tmp_dest" "$backup_dest"

  if command -v rsync >/dev/null 2>&1; then
    mkdir -p "$tmp_dest"
    rsync -a --delete "$source_dir/" "$tmp_dest/"
  else
    cp -R "$source_dir" "$tmp_dest"
  fi

  if [[ -d "$PLUGIN_DEST" ]]; then
    mv "$PLUGIN_DEST" "$backup_dest"
  fi

  if mv "$tmp_dest" "$PLUGIN_DEST"; then
    rm -rf "$backup_dest"
  else
    rm -rf "$PLUGIN_DEST"
    if [[ -d "$backup_dest" ]]; then
      mv "$backup_dest" "$PLUGIN_DEST"
    fi
    rm -rf "$tmp_dest"
    return 1
  fi
}

install_support_files() {
  local support_dir="$1"
  local backup_dir="$2"
  mkdir -p "$BIN_DIR" "$backup_dir"
  for file in "$support_dir"/*; do
    [[ -f "$file" ]] || continue
    local support_name support_dest
    support_name="$(basename "$file")"
    support_dest="$BIN_DIR/$support_name"
    if [[ "$support_name" == "update-team-skills.sh" || "$support_name" == "refresh-team-skills.command" ]]; then
      cp "$file" "$support_dest.next"
      chmod +x "$support_dest.next"
      continue
    fi
    if [[ -f "$support_dest" ]]; then
      cp "$support_dest" "$backup_dir/$support_name"
    fi
    cp "$file" "$support_dest"
    case "$support_name" in
      *.sh|*.command|*.py)
        chmod +x "$support_dest"
        ;;
    esac
  done
}

write_state() {
  local product_version="$1"
  local runtime_version="$2"
  local release_id="$3"
  local commit="$4"
  local channel="$5"
  local bundle_url="$6"
  local signature_state="$7"
  python3 - "$STATE_PATH" "$product_version" "$runtime_version" "$release_id" "$commit" "$channel" "$bundle_url" "$PLUGIN_DEST" "$MARKETPLACE_PATH" "$CODEX_CONFIG_PATH" "$UPDATER_VERSION" "$signature_state" "$CODEX_PLUGIN_CACHE_DIR" "$INVALIDATED_CODEX_PLUGIN_CACHE" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1]).expanduser()
path.parent.mkdir(parents=True, exist_ok=True)
data = {
    "last_success_at": datetime.now(timezone.utc).isoformat(),
    "product_version": sys.argv[2],
    "runtime_version": sys.argv[3],
    "release_id": sys.argv[4],
    "commit": sys.argv[5],
    "channel": sys.argv[6],
    "bundle_url": sys.argv[7],
    "plugin_path": sys.argv[8],
    "marketplace_path": sys.argv[9],
    "codex_config_path": sys.argv[10],
    "updater_version": sys.argv[11],
    "signature_verification": sys.argv[12],
    "codex_plugin_cache_path": sys.argv[13],
    "codex_plugin_cache_invalidated_path": sys.argv[14],
    "runtime_visibility": "requires Codex restart after plugin swap and Codex cache invalidation; cannot be proven from shell",
}
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

repair_install() {
  require_python3
  if [[ ! -f "$PLUGIN_DEST/.codex-plugin/plugin.json" ]]; then
    log "Repair не применён: plugin не найден: $PLUGIN_DEST"
    exit 1
  fi
  update_marketplace
  update_codex_registry
  invalidate_codex_plugin_cache
  read -r PRODUCT_VERSION RUNTIME_VERSION < <(python3 - "$PLUGIN_DEST/.codex-plugin/plugin.json" <<'PY'
import json, sys
from pathlib import Path
manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
version = manifest.get("version", "")
print(manifest.get("product_version", version), version)
PY
)
  write_state "$PRODUCT_VERSION" "$RUNTIME_VERSION" "repair-install" "" "local" "" "repair-no-download"
  log "Repair завершён: Codex registry настроен. Перезапустите Codex."
}

if [[ "$MODE" == "repair" ]]; then
  repair_install
  exit 0
fi

require_python3
mkdir -p "$CACHE_DIR" "$STATE_DIR" "$LOG_DIR" "$BIN_DIR"
WORK_DIR="$(mktemp -d "$CACHE_DIR/work.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT

LATEST_FILE="$WORK_DIR/latest.json"
MANIFEST_FILE="$WORK_DIR/manifest.json"
BUNDLE_FILE="$WORK_DIR/team-skills-bundle.zip"
EXPANDED_DIR="$WORK_DIR/expanded"
SUPPORT_DIR="$WORK_DIR/support"
SUPPORT_BACKUP_DIR="$WORK_DIR/support-backup"

if [[ -z "$MANIFEST_URL" ]]; then
  log "Скачиваю signed latest.json."
  download_signed "$LATEST_URL" "$LATEST_FILE"
  MANIFEST_URL="$(python3 - "$LATEST_FILE" <<'PY'
import json, sys
from pathlib import Path
latest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(latest["manifest_url"])
PY
)"
fi

log "Скачиваю signed manifest.json."
download_signed "$MANIFEST_URL" "$MANIFEST_FILE"

read -r BUNDLE_URL BUNDLE_SHA PRODUCT_VERSION RUNTIME_VERSION RELEASE_ID COMMIT CHANNEL MIN_BOOTSTRAP < <(python3 - "$MANIFEST_FILE" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
bundle = manifest["plugin_bundle"]
print(
    bundle["url"],
    bundle["sha256"],
    manifest.get("product_version", ""),
    manifest.get("runtime_version", ""),
    manifest.get("release_id", ""),
    manifest.get("commit", ""),
    manifest.get("channel", "stable"),
    manifest.get("minimum_bootstrap_version", ""),
)
PY
)

log "Скачиваю plugin bundle."
curl -fsSL "$BUNDLE_URL" -o "$BUNDLE_FILE"
verify_sha256 "$BUNDLE_FILE" "$BUNDLE_SHA"

mkdir -p "$SUPPORT_DIR"
python3 - "$MANIFEST_FILE" <<'PY' | while IFS=$'\t' read -r NAME URL SHA256; do
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for entry in manifest.get("support_files", []):
    print(f"{entry['name']}\t{entry['url']}\t{entry['sha256']}")
PY
  [[ -n "$NAME" ]] || continue
  curl -fsSL "$URL" -o "$SUPPORT_DIR/$NAME"
  verify_sha256 "$SUPPORT_DIR/$NAME" "$SHA256"
done

mkdir -p "$EXPANDED_DIR"
unzip -q "$BUNDLE_FILE" -d "$EXPANDED_DIR"
PLUGIN_ROOT="$(find_plugin_root "$EXPANDED_DIR")" || {
  log "Обновление не применено: в bundle нет .codex-plugin/plugin.json."
  exit 1
}

python3 - "$PLUGIN_ROOT/.codex-plugin/plugin.json" "$RUNTIME_VERSION" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
expected_runtime = sys.argv[2]
manifest = json.loads(path.read_text(encoding="utf-8"))
if manifest.get("version") != expected_runtime:
    raise SystemExit(f"runtime_version mismatch: plugin={manifest.get('version')} manifest={expected_runtime}")
PY

update_marketplace
update_codex_registry
swap_plugin "$PLUGIN_ROOT"
install_support_files "$SUPPORT_DIR" "$SUPPORT_BACKUP_DIR" >/dev/null
invalidate_codex_plugin_cache
write_state "$PRODUCT_VERSION" "$RUNTIME_VERSION" "$RELEASE_ID" "$COMMIT" "$CHANNEL" "$BUNDLE_URL" "signed"

log "Установлена проверенная версия team-skills: product=$PRODUCT_VERSION runtime=$RUNTIME_VERSION release=$RELEASE_ID."
log "Перезапустите Codex, чтобы он перечитал plugin после cache invalidation; runtime visibility cannot be proven from shell."
