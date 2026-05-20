#!/usr/bin/env zsh
set -euo pipefail

PLUGIN_NAME="team-skills"
RELEASE_BASE="https://github.com/kir-kopylov/codex-team-skills/releases/latest/download"
MANIFEST_URL="${CODEX_TEAM_SKILLS_MANIFEST_URL:-$RELEASE_BASE/manifest.json}"
INSTALL_ROOT="${CODEX_TEAM_SKILLS_HOME:-$HOME/Library/Application Support/CodexTeamSkills}"
CACHE_DIR="$INSTALL_ROOT/cache"
STATE_DIR="$INSTALL_ROOT/state"
LOG_DIR="$INSTALL_ROOT/logs"
PLUGIN_DEST="${CODEX_TEAM_SKILLS_PLUGIN_DIR:-$HOME/plugins/team-skills}"
MARKETPLACE_PATH="${CODEX_TEAM_SKILLS_MARKETPLACE:-$HOME/.agents/plugins/marketplace.json}"
STATE_PATH="$STATE_DIR/state.json"
LOG_PATH="$LOG_DIR/team-skills-update.log"

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
    log "Обновление не применено: нужен python3 для проверки manifest и marketplace."
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

require_python3
mkdir -p "$CACHE_DIR" "$STATE_DIR" "$LOG_DIR"
WORK_DIR="$(mktemp -d "$CACHE_DIR/work.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT

MANIFEST_FILE="$WORK_DIR/manifest.json"
BUNDLE_FILE="$WORK_DIR/team-skills-bundle.zip"
EXPANDED_DIR="$WORK_DIR/expanded"

log "Скачиваю manifest проверенного release-bundle."
curl -fsSL "$MANIFEST_URL" -o "$MANIFEST_FILE"

read -r BUNDLE_URL SHA256 VERSION COMMIT < <(python3 - "$MANIFEST_FILE" "$RELEASE_BASE" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
release_base = sys.argv[2]
bundle_url = manifest.get("bundle_url") or f"{release_base}/team-skills-bundle.zip"
sha256 = manifest.get("sha256") or ""
if not sha256:
    raise SystemExit("manifest.json не содержит sha256")
print(bundle_url, sha256, manifest.get("version", ""), manifest.get("commit", ""))
PY
)

log "Скачиваю team-skills-bundle.zip."
curl -fsSL "$BUNDLE_URL" -o "$BUNDLE_FILE"
ACTUAL_SHA="$(shasum -a 256 "$BUNDLE_FILE" | awk '{print tolower($1)}')"
EXPECTED_SHA="$(printf '%s' "$SHA256" | tr '[:upper:]' '[:lower:]')"
if [[ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]]; then
  log "Обновление не применено: checksum mismatch."
  exit 1
fi

mkdir -p "$EXPANDED_DIR"
unzip -q "$BUNDLE_FILE" -d "$EXPANDED_DIR"
PLUGIN_ROOT="$(find_plugin_root "$EXPANDED_DIR")" || {
  log "Обновление не применено: в bundle нет .codex-plugin/plugin.json."
  exit 1
}

swap_plugin "$PLUGIN_ROOT"
update_marketplace

python3 - "$STATE_PATH" "$VERSION" "$COMMIT" "$SHA256" "$PLUGIN_DEST" "$MARKETPLACE_PATH" "$BUNDLE_URL" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1]).expanduser()
path.parent.mkdir(parents=True, exist_ok=True)
data = {
    "last_success_at": datetime.now(timezone.utc).isoformat(),
    "version": sys.argv[2],
    "commit": sys.argv[3],
    "sha256": sys.argv[4],
    "plugin_path": sys.argv[5],
    "marketplace_path": sys.argv[6],
    "bundle_url": sys.argv[7],
}
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

log "Установлена проверенная версия team-skills: version=$VERSION, commit=$COMMIT."
