# Хороший Пример: Уборка Веток После Merge

## Вход

«PR смержен. Убери локальные и remote ветки, чтобы не было branch clutter.»

## Ожидаемое Поведение

Codex сначала проверяет `status`, `branch -vv`, `branch --merged origin/main`, remote branches и PR state. Merged локальные ветки удаляются через `branch -d`, merged remote branches — через `push origin --delete`. Если remote branch не merged или PR не найден, Codex не удаляет её автоматически: показывает commit, diff относительно `origin/main`, возраст и рекомендует keep/delete/rebuild. После cleanup Codex делает `fetch --prune` и показывает финальную remote-карту.

## Нельзя

Нельзя удалять unmerged remote branch только потому, что она выглядит старой. Нельзя использовать `branch -D` до доказательства, что работа сохранена или superseded. Нельзя считать cleanup завершенным без финального `status` и списка remote branches.
