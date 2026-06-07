#!/usr/bin/env bash
# pull-skills.sh — устанавливает командные скиллы для Claude Code.
#
# Тянет свежий main из клона репозитория, затем копирует скиллы в личную
# папку ~/.claude/skills/, откуда их читают ОБЕ поверхности Claude Code
# (десктоп-приложение и CLI). Маркетплейс/плагины не нужны.
#
# Гарантии безопасности:
#  - git pull --ff-only: при разошедшемся/грязном клоне НЕ ломает дерево —
#    просто работает на текущем состоянии и пишет предупреждение;
#  - prune ТОЛЬКО по маркеру .team-skill: личные скиллы коллег, которых нет
#    в репозитории, никогда не удаляются;
#  - битый frontmatter в SKILL.md → скилл пропускается (fail-closed), а не
#    копируется и не валит весь синк (паритет с tests/test_skill_structure.py).
#
# Логирование: весь вывод идёт в stdout/stderr; SessionStart-hook
# перенаправляет его в ~/.claude/skills/.sync.log. Плюс пишется компактный
# маркер ~/.claude/skills/.last-sync (HEAD + счётчики) для проверки свежести.
#
# Переменные окружения:
#  - CLAUDE_SKILLS_DIR : куда устанавливать (по умолчанию ~/.claude/skills)
#  - TEAM_SKILLS_PULL  : "1" (по умолчанию) — делать git pull; "0" — пропустить
#                        (тесты выставляют 0 для детерминизма без сети).
#
# Коды выхода: 0 — ок (в т.ч. с пропусками); 1 — нечего устанавливать.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/plugins/team-skills/skills"
DEST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
MARKER=".team-skill"

mkdir -p "$DEST"

ts()  { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { printf '%s %s\n' "$(ts)" "$1"; }          # -> stdout (hook пишет в .sync.log)
err() { printf '%s %s\n' "$(ts)" "$1" >&2; }      # -> stderr

log "=== pull-skills start ==="

# 1. Подтянуть свежий main — best-effort, неблокирующе и отключаемо.
if [[ "${TEAM_SKILLS_PULL:-1}" == "1" ]]; then
  if git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
    if git -C "$ROOT" pull --ff-only origin main; then
      log "git pull --ff-only origin main: ok ($(git -C "$ROOT" rev-parse --short HEAD))"
    else
      log "ВНИМАНИЕ: git pull --ff-only не прошёл (offline/diverged); работаю на текущем клоне $(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo '?')"
    fi
  else
    log "ВНИМАНИЕ: $ROOT не git-репозиторий; pull пропущен"
  fi
else
  log "git pull пропущен (TEAM_SKILLS_PULL=0)"
fi

if [[ ! -d "$SRC" ]]; then
  err "Не найдена папка скиллов репозитория: $SRC"
  exit 1
fi

# 2. Валидатор frontmatter без зависимостей (PyYAML на runtime может не быть).
#    Зеркалит структурные проверки tests/test_skill_structure.py:
#    frontmatter есть, top-level ключи ⊆ allowed, name == имя папки, name по NAME_RE.
valid_frontmatter() {
  python3 - "$1" "$2" <<'PY'
import re, sys
path, expected = sys.argv[1], sys.argv[2]
allowed = {"name", "description", "license", "allowed-tools", "metadata"}
name_re = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
try:
    text = open(path, encoding="utf-8").read()
except Exception:
    sys.exit(1)
m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
if not m:
    sys.exit(1)
fm = m.group(1)
keys = re.findall(r"^([A-Za-z0-9_-]+):", fm, re.MULTILINE)
if not keys or not set(keys) <= allowed:
    sys.exit(1)
mn = re.search(r"^name:\s*(.+?)\s*$", fm, re.MULTILINE)
nm = mn.group(1).strip().strip('"\'') if mn else ""
if nm != expected or not name_re.match(nm):
    sys.exit(1)
if "description" not in keys:
    sys.exit(1)
sys.exit(0)
PY
}

log "Источник:   $SRC"
log "Назначение: $DEST"

# 3. Копирование с маркером + fail-closed гейтом.
count=0; skipped=0
for skill_dir in "$SRC"/*/; do
  [[ -f "${skill_dir}SKILL.md" ]] || continue
  name="$(basename "$skill_dir")"
  [[ -n "$name" ]] || continue
  if ! valid_frontmatter "${skill_dir}SKILL.md" "$name"; then
    log "  ⤫ ПРОПУСК $name — невалидный frontmatter (keys/name); не копирую (fail-closed)"
    skipped=$((skipped + 1))
    continue
  fi
  rm -rf "${DEST:?}/${name}"
  cp -R "$skill_dir" "$DEST/$name"
  : > "$DEST/$name/$MARKER"          # sentinel: установлено этим скриптом
  count=$((count + 1))
  log "  ✓ $name"
done

# 4. Prune — только наши осиротевшие скиллы (есть маркер, нет в репо).
#    Скиллы без маркера (личные/чужие) НЕ трогаем.
pruned=0
for dest_dir in "$DEST"/*/; do
  [[ -d "$dest_dir" ]] || continue
  dname="$(basename "$dest_dir")"
  [[ -f "${dest_dir}${MARKER}" ]] || continue
  if [[ -d "$SRC/$dname" && -f "$SRC/$dname/SKILL.md" ]]; then
    continue
  fi
  rm -rf "${DEST:?}/${dname}"
  pruned=$((pruned + 1))
  log "  ✗ prune $dname (удалён из репозитория)"
done

# 5. Маркер свежести для team-skills-maintenance.
printf '%s head=%s installed=%s skipped=%s pruned=%s\n' \
  "$(ts)" "$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo '?')" \
  "$count" "$skipped" "$pruned" > "$DEST/.last-sync" 2>/dev/null || true

if [[ "$count" -eq 0 ]]; then
  err "Скиллов с SKILL.md не найдено — ничего не установлено."
  exit 1
fi

log "Готово: установлено скиллов — $count (пропущено $skipped, удалено $pruned)."
log "Если скилл не появился сразу — перезапустите Claude (приложение или сессию CLI)."
log "=== pull-skills end ==="
exit 0
