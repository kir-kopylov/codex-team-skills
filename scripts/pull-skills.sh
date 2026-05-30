#!/usr/bin/env bash
# pull-skills.sh — устанавливает командные скиллы для Claude Code.
#
# Копирует скиллы из репозитория в личную папку ~/.claude/skills/,
# откуда их читают ОБЕ поверхности Claude Code: и десктоп-приложение,
# и терминальный CLI. Маркетплейс/плагины не нужны.
#
# Запуск:  ./scripts/pull-skills.sh
# Повторный запуск безопасен — просто обновляет скиллы из репозитория.
#
# Трогает ТОЛЬКО скиллы, которые есть в репозитории. Личные скиллы
# коллеги, которых нет в репозитории, не удаляются и не меняются.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/plugins/team-skills/skills"
DEST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"

if [[ ! -d "$SRC" ]]; then
  echo "Не найдена папка скиллов репозитория: $SRC" >&2
  exit 1
fi

mkdir -p "$DEST"

echo "Источник:  $SRC"
echo "Назначение: $DEST"
echo "Устанавливаю скиллы:"

count=0
for skill_dir in "$SRC"/*/; do
  [[ -f "${skill_dir}SKILL.md" ]] || continue
  name="$(basename "$skill_dir")"
  [[ -n "$name" ]] || continue
  rm -rf "${DEST:?}/${name}"
  cp -R "$skill_dir" "$DEST/$name"
  echo "  ✓ $name"
  count=$((count + 1))
done

if [[ "$count" -eq 0 ]]; then
  echo "Скиллов с SKILL.md не найдено — ничего не установлено." >&2
  exit 1
fi

echo
echo "Готово: установлено скиллов — $count."
echo "Если скилл не появился сразу, перезапустите Claude (приложение или сессию CLI)."
