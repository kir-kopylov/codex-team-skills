# Хороший Пример

## Вход

«Хочу убрать remote branch clutter. Осталась ветка `origin/claude/claude-md-docs-n11Uo`. Что это и можно ли удалить?»

## Ожидаемое Поведение

Codex не удаляет ветку сразу. Он проверяет `branch -r --merged`, `branch -r --no-merged`, commit log, diff относительно `origin/main`, PR state через GitHub и содержимое файлов, если нужно понять ценность. Если ветка не merged, PR не найден, diff старый и пользователь явно решает, что guide не нужен, Codex удаляет remote branch и делает `fetch --prune`. В финале показывает, что remote branches сведены к `origin/main`.

## Нельзя

Нельзя считать `branch -r` clutter достаточным доказательством для удаления. Нельзя удалять unmerged remote branch без классификации и явного решения пользователя. Нельзя merge'ить stale branch как есть, если документ устарел.
