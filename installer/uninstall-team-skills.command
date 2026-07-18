#!/usr/bin/env zsh
set -euo pipefail

PLUGIN_NAME="team-skills"
LEGACY_INSTALL_ROOT="$HOME/Library/Application Support/CodexTeamSkills"
LEGACY_PLIST="$HOME/Library/LaunchAgents/com.codex-team-skills.autoupdate.plist"
PLUGIN_DEST="${CODEX_TEAM_SKILLS_PLUGIN_DIR:-$HOME/plugins/team-skills}"
MARKETPLACE_PATH="${CODEX_TEAM_SKILLS_MARKETPLACE:-$HOME/.agents/plugins/marketplace.json}"
CODEX_CONFIG_PATH="${CODEX_TEAM_SKILLS_CODEX_CONFIG:-$HOME/.codex/config.toml}"
CODEX_PLUGIN_CACHE_DIR="${CODEX_TEAM_SKILLS_CODEX_PLUGIN_CACHE_DIR:-$HOME/.codex/plugins/cache/codex-team-skills}"

info() {
  printf '[team-skills] %s\n' "$1"
}

fail() {
  info "$1"
  exit 1
}

safe_remove_tree() {
  local target_path="$1"
  local resolved="${target_path:A}"
  local home_resolved="${HOME:A}"
  [[ -n "$resolved" && "$resolved" != "/" && "$resolved" != "$home_resolved" ]] || \
    fail "Небезопасный путь для удаления: $target_path"
  rm -rf -- "$target_path"
  [[ ! -e "$target_path" ]] || fail "Не удалось удалить: $target_path"
}

command -v python3 >/dev/null 2>&1 || fail "Для полного удаления нужен Python 3.11 или новее."
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' || \
  fail "Для полного удаления нужен Python 3.11 или новее."

LEGACY_MARKER_FOUND=0
for marker in bootstrap-team-skills.sh update-team-skills.sh update-team-skills-with-cache-reset.sh; do
  [[ -f "$LEGACY_INSTALL_ROOT/bin/$marker" ]] && LEGACY_MARKER_FOUND=1
done
if [[ -e "$LEGACY_PLIST" || "$LEGACY_MARKER_FOUND" == "1" ]]; then
  fail "Сначала запустите remove-team-skills-autoupdate.command --dry-run, затем --apply. Полный uninstall не удаляет legacy updater."
fi

python3 - "$MARKETPLACE_PATH" "$CODEX_CONFIG_PATH" "$PLUGIN_NAME" <<'PY'
import json
import os
import shutil
import sys
import tempfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path

marketplace_path = Path(sys.argv[1]).expanduser()
config_path = Path(sys.argv[2]).expanduser()
plugin_name = sys.argv[3]
begin = "# BEGIN codex-team-skills managed block"
end = "# END codex-team-skills managed block"
targets = {"[marketplaces.codex-team-skills]", '[plugins."team-skills@codex-team-skills"]'}


def backup(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = path.with_name(f"{path.name}.codex-team-skills.bak.{stamp}")
    shutil.copy2(path, destination)
    return destination


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def strip_managed_content(text: str) -> str:
    lines = text.splitlines()
    kept: list[str] = []
    rescued: list[str] = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped == begin:
            index += 1
            while index < len(lines) and lines[index].strip() != end:
                header = lines[index].strip()
                if header.startswith("[") and header not in targets:
                    rescued.append(lines[index])
                    index += 1
                    while index < len(lines) and lines[index].strip() != end and not lines[index].lstrip().startswith("["):
                        rescued.append(lines[index])
                        index += 1
                else:
                    index += 1
            if index < len(lines):
                index += 1
            continue
        if stripped in targets:
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


if marketplace_path.exists():
    data = json.loads(marketplace_path.read_text(encoding="utf-8-sig"))
    data["plugins"] = [entry for entry in data.get("plugins", []) if entry.get("name") != plugin_name]
    marketplace_backup = backup(marketplace_path)
    try:
        atomic_write(marketplace_path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    except Exception:
        shutil.copy2(marketplace_backup, marketplace_path)
        raise

if config_path.exists():
    next_text = strip_managed_content(config_path.read_text(encoding="utf-8-sig"))
    tomllib.loads(next_text or "\n")
    config_backup = backup(config_path)
    try:
        atomic_write(config_path, next_text)
        tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        shutil.copy2(config_backup, config_path)
        raise
PY

[[ ! -f "$MARKETPLACE_PATH" ]] || info "Запись team-skills удалена из marketplace."
[[ ! -f "$CODEX_CONFIG_PATH" ]] || info "Запись team-skills удалена из Codex registry."

if [[ -d "$PLUGIN_DEST" ]]; then
  safe_remove_tree "$PLUGIN_DEST"
  info "Локальный plugin team-skills удалён."
fi

if [[ -d "$CODEX_PLUGIN_CACHE_DIR" ]]; then
  safe_remove_tree "$CODEX_PLUGIN_CACHE_DIR"
  info "Codex plugin cache team-skills удалён."
fi

info "Удаление завершено. Перезапустите Codex, чтобы он перечитал список plugin."
