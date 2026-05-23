#!/usr/bin/env zsh
set -euo pipefail

RELEASE_BASE="https://github.com/kir-kopylov/codex-team-skills/releases/latest/download"
INSTALL_ROOT="${CODEX_TEAM_SKILLS_HOME:-$HOME/Library/Application Support/CodexTeamSkills}"
BIN_DIR="$INSTALL_ROOT/bin"
BOOTSTRAP_SCRIPT="$BIN_DIR/bootstrap-team-skills.sh"

info() {
  printf '[team-skills] %s\n' "$1"
}

mkdir -p "$BIN_DIR" "$INSTALL_ROOT/logs"

install_support_file() {
  local name="$1"
  local source_dir
  source_dir="$(cd "$(dirname "$0")" && pwd)"
  if [[ -f "$source_dir/$name" ]]; then
    cp "$source_dir/$name" "$BIN_DIR/$name"
  else
    info "Скачиваю служебный файл $name"
    curl -fsSL "$RELEASE_BASE/$name" -o "$BIN_DIR/$name"
  fi
  chmod +x "$BIN_DIR/$name"
}

install_support_file "bootstrap-team-skills.sh"
install_support_file "update-team-skills.sh"
install_support_file "uninstall-team-skills.command"
install_support_file "team-skills-status.command"
install_support_file "team-skills-registry.py"
install_support_file "team-skills-public-key.pem"

info "Ставлю последнюю проверенную версию командных Codex skills."
"$BOOTSTRAP_SCRIPT"

PLIST_PATH="$HOME/Library/LaunchAgents/com.codex-team-skills.autoupdate.plist"
mkdir -p "$(dirname "$PLIST_PATH")" "$HOME/Library/Logs"

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.codex-team-skills.autoupdate</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>$BOOTSTRAP_SCRIPT</string>
  </array>
  <key>StartInterval</key>
  <integer>172800</integer>
  <key>RunAtLoad</key>
  <false/>
  <key>StandardOutPath</key>
  <string>$HOME/Library/Logs/codex-team-skills-autoupdate.log</string>
  <key>StandardErrorPath</key>
  <string>$HOME/Library/Logs/codex-team-skills-autoupdate.err</string>
</dict>
</plist>
PLIST

launchctl unload "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl load "$PLIST_PATH" >/dev/null 2>&1 || true

info "Автообновление включено: macOS LaunchAgent, раз в двое суток."
info "Готово. Перезапустите Codex, чтобы он перечитал plugin team-skills."
