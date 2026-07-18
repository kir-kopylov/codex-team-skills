#!/usr/bin/env zsh
set -euo pipefail

PLUGIN_NAME="team-skills"
MARKETPLACE_NAME="codex-team-skills"
RELEASE_BASE="https://github.com/kir-kopylov/codex-team-skills/releases/latest/download"
LATEST_URL="${CODEX_TEAM_SKILLS_LATEST_URL:-$RELEASE_BASE/latest.json}"
MANIFEST_URL="${CODEX_TEAM_SKILLS_MANIFEST_URL:-}"
INSTALL_ROOT="${CODEX_TEAM_SKILLS_HOME:-$HOME/Library/Application Support/CodexTeamSkills}"
BIN_DIR="$INSTALL_ROOT/bin"
PLUGIN_DEST="${CODEX_TEAM_SKILLS_PLUGIN_DIR:-$HOME/plugins/team-skills}"
MARKETPLACE_ROOT="${CODEX_TEAM_SKILLS_MARKETPLACE_ROOT:-$HOME}"
MARKETPLACE_PATH="${CODEX_TEAM_SKILLS_MARKETPLACE:-$MARKETPLACE_ROOT/.agents/plugins/marketplace.json}"
CODEX_CONFIG_PATH="${CODEX_TEAM_SKILLS_CODEX_CONFIG:-$HOME/.codex/config.toml}"
CODEX_PLUGIN_CACHE_DIR="${CODEX_TEAM_SKILLS_CODEX_PLUGIN_CACHE_DIR:-$HOME/.codex/plugins/cache/$MARKETPLACE_NAME}"
EXPECTED_PUBLIC_KEY_SHA256="6303efaa119fef81c5c40a281e85998351aa5c7a81100e00e4921198403371a6"
VALIDATE_ONLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --manifest-url)
      MANIFEST_URL="${2:-}"
      shift 2
      ;;
    --latest-url)
      LATEST_URL="${2:-}"
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
  info "$1"
  exit 1
}

if [[ "$VALIDATE_ONLY" == "1" ]]; then
  info "ValidateOnly: install-team-skills.command parsed and initialized."
  exit 0
fi

for command_name in curl python3 unzip; do
  command -v "$command_name" >/dev/null 2>&1 || fail "Для установки нужен $command_name."
done
command -v openssl >/dev/null 2>&1 || fail "Для проверки подписи нужен openssl."
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' || \
  fail "Для установки нужен Python 3.11 или новее."

remove_legacy_updater() {
  local legacy_plist="$HOME/Library/LaunchAgents/com.codex-team-skills.autoupdate.plist"
  local legacy_service="gui/$UID/com.codex-team-skills.autoupdate"
  launchctl unload "$legacy_plist" >/dev/null 2>&1 || true
  launchctl bootout "$legacy_service" >/dev/null 2>&1 || true
  rm -f "$legacy_plist" \
    "$HOME/Library/Logs/codex-team-skills-autoupdate.log" \
    "$HOME/Library/Logs/codex-team-skills-autoupdate.err" \
    "$BIN_DIR/bootstrap-team-skills.sh" \
    "$BIN_DIR/update-team-skills.sh" \
    "$BIN_DIR/update-team-skills.sh.next" \
    "$BIN_DIR/team-skills-status.command" \
    "$BIN_DIR/refresh-team-skills.command" \
    "$BIN_DIR/refresh-team-skills.command.next"
  rm -rf "$INSTALL_ROOT/cache" "$INSTALL_ROOT/state" "$INSTALL_ROOT/logs"
  if launchctl print "$legacy_service" >/dev/null 2>&1; then
    fail "Не удалось остановить старый LaunchAgent Team Skills."
  fi
}

remove_legacy_updater

file_sha256() {
  local file_path="$1"
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$file_path" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$file_path" | awk '{print $1}'
  else
    openssl dgst -sha256 "$file_path" | awk '{print $NF}'
  fi
}

verify_sha256() {
  local file_path="$1"
  local expected="$2"
  local actual
  actual="$(file_sha256 "$file_path" | tr '[:upper:]' '[:lower:]')"
  expected="$(printf '%s' "$expected" | tr '[:upper:]' '[:lower:]')"
  [[ "$actual" == "$expected" ]] || fail "Checksum mismatch для $(basename "$file_path")."
}

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/codex-team-skills-install.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT
PUBLIC_KEY_PATH="$WORK_DIR/team-skills-public-key.pem"
SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ -n "${CODEX_TEAM_SKILLS_PUBLIC_KEY:-}" ]]; then
  cp "$CODEX_TEAM_SKILLS_PUBLIC_KEY" "$PUBLIC_KEY_PATH"
elif [[ -f "$SOURCE_DIR/team-skills-public-key.pem" ]]; then
  cp "$SOURCE_DIR/team-skills-public-key.pem" "$PUBLIC_KEY_PATH"
else
  info "Скачиваю public key."
  curl -fsSL "$RELEASE_BASE/team-skills-public-key.pem" -o "$PUBLIC_KEY_PATH"
fi
verify_sha256 "$PUBLIC_KEY_PATH" "$EXPECTED_PUBLIC_KEY_SHA256"

verify_signature() {
  local payload="$1"
  local signature="$2"
  openssl dgst -sha256 -verify "$PUBLIC_KEY_PATH" -signature "$signature" "$payload" >/dev/null || \
    fail "Подпись $(basename "$payload") недействительна."
}

download_signed() {
  local url="$1"
  local destination="$2"
  curl -fsSL "$url" -o "$destination"
  curl -fsSL "$url.sig" -o "$destination.sig"
  verify_signature "$destination" "$destination.sig"
}

LATEST_FILE="$WORK_DIR/latest.json"
MANIFEST_FILE="$WORK_DIR/manifest.json"
BUNDLE_FILE="$WORK_DIR/team-skills-bundle.zip"
EXPANDED_DIR="$WORK_DIR/expanded"
SUPPORT_DIR="$WORK_DIR/support"
mkdir -p "$EXPANDED_DIR" "$SUPPORT_DIR"

if [[ -z "$MANIFEST_URL" ]]; then
  info "Скачиваю подписанный указатель release."
  download_signed "$LATEST_URL" "$LATEST_FILE"
  MANIFEST_URL="$(python3 - "$LATEST_FILE" <<'PY'
import json
import sys
from pathlib import Path

print(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["manifest_url"])
PY
)"
fi

info "Скачиваю подписанный manifest."
download_signed "$MANIFEST_URL" "$MANIFEST_FILE"

IFS=$'\t' read -r BUNDLE_URL BUNDLE_SHA PRODUCT_VERSION RUNTIME_VERSION RELEASE_ID < <(python3 - "$MANIFEST_FILE" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
bundle = manifest["plugin_bundle"]
print("\t".join([
    bundle["url"],
    bundle["sha256"],
    manifest.get("product_version", ""),
    manifest.get("runtime_version", ""),
    manifest.get("release_id", ""),
]))
PY
)

info "Скачиваю plugin bundle."
curl -fsSL "$BUNDLE_URL" -o "$BUNDLE_FILE"
verify_sha256 "$BUNDLE_FILE" "$BUNDLE_SHA"
unzip -q "$BUNDLE_FILE" -d "$EXPANDED_DIR"

PLUGIN_ROOT=""
for candidate in "$EXPANDED_DIR/team-skills" "$EXPANDED_DIR/plugins/team-skills" "$EXPANDED_DIR"; do
  if [[ -f "$candidate/.codex-plugin/plugin.json" ]]; then
    PLUGIN_ROOT="$candidate"
    break
  fi
done
[[ -n "$PLUGIN_ROOT" ]] || fail "В bundle не найден plugin team-skills."

python3 - "$PLUGIN_ROOT/.codex-plugin/plugin.json" "$RUNTIME_VERSION" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if manifest.get("version") != sys.argv[2]:
    raise SystemExit("runtime_version в bundle не совпадает с manifest")
PY

download_support_file() {
  local name="$1"
  local destination="$SUPPORT_DIR/$name"
  local metadata url expected
  metadata="$(python3 - "$MANIFEST_FILE" "$name" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for entry in manifest.get("support_files", []):
    if entry.get("name") == sys.argv[2]:
        print(f"{entry['url']}\t{entry['sha256']}")
        break
else:
    raise SystemExit(f"support file отсутствует: {sys.argv[2]}")
PY
)"
  IFS=$'\t' read -r url expected <<< "$metadata"
  curl -fsSL "$url" -o "$destination"
  verify_sha256 "$destination" "$expected"
}

for support_name in team-skills-registry.py uninstall-team-skills.command; do
  download_support_file "$support_name"
done

python3 - "$MARKETPLACE_PATH" "$PLUGIN_NAME" "$PLUGIN_DEST" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1]).expanduser()
path.parent.mkdir(parents=True, exist_ok=True)
data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
    "name": "local-team-skills",
    "interface": {"displayName": "Локальные командные skills"},
    "plugins": [],
}
plugins = [entry for entry in data.setdefault("plugins", []) if entry.get("name") != sys.argv[2]]
plugins.append({
    "name": sys.argv[2],
    "source": {"source": "local", "path": str(Path(sys.argv[3]).expanduser()).replace("\\", "/")},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    "category": "Productivity",
})
data["plugins"] = plugins
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

python3 "$SUPPORT_DIR/team-skills-registry.py" ensure \
  --config "$CODEX_CONFIG_PATH" \
  --marketplace-root "$MARKETPLACE_ROOT" >/dev/null

TMP_DEST="$PLUGIN_DEST.tmp.$$"
BACKUP_DEST="$PLUGIN_DEST.previous.$$"
mkdir -p "$(dirname "$PLUGIN_DEST")"
rm -rf "$TMP_DEST" "$BACKUP_DEST"
cp -R "$PLUGIN_ROOT" "$TMP_DEST"
if [[ -d "$PLUGIN_DEST" ]]; then
  mv "$PLUGIN_DEST" "$BACKUP_DEST"
fi
if mv "$TMP_DEST" "$PLUGIN_DEST"; then
  rm -rf "$BACKUP_DEST"
else
  rm -rf "$PLUGIN_DEST" "$TMP_DEST"
  [[ ! -d "$BACKUP_DEST" ]] || mv "$BACKUP_DEST" "$PLUGIN_DEST"
  fail "Не удалось заменить plugin; прежняя версия восстановлена."
fi

if [[ -d "$CODEX_PLUGIN_CACHE_DIR" && "$CODEX_PLUGIN_CACHE_DIR" != "/" && "$CODEX_PLUGIN_CACHE_DIR" != "$HOME" ]]; then
  mv "$CODEX_PLUGIN_CACHE_DIR" "$CODEX_PLUGIN_CACHE_DIR.stale.$(date -u +%Y%m%dT%H%M%SZ).$$"
fi

mkdir -p "$BIN_DIR"
for support_name in team-skills-registry.py uninstall-team-skills.command; do
  cp "$SUPPORT_DIR/$support_name" "$BIN_DIR/$support_name"
done
chmod +x "$BIN_DIR/team-skills-registry.py" "$BIN_DIR/uninstall-team-skills.command"

info "Установлена проверенная версия team-skills: product=$PRODUCT_VERSION runtime=$RUNTIME_VERSION release=$RELEASE_ID."
info "Автообновления нет: для новой версии повторно запустите эту же команду установки."
info "Перезапустите Codex, чтобы он перечитал plugin."
