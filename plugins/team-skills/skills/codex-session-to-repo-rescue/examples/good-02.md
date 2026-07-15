# Хороший Пример: Только Название Task И Read-Only Проверка

## Вход

«Проверь, не пропала ли работа из task “Исследовать перенос отчётности”. Ничего пока не коммить и не публикуй».

## Ожидаемое Поведение

Skill выбирает режим `map-only`. Через доступный Codex task tool разрешает название в точный `thread_id`, затем потоково находит session file и извлекает подтверждённый `cwd`. Если `cwd` — workspace-контейнер, ограниченно читает tool metadata и находит связанный worktree по `workdir`/absolute path hints. Проверяет candidate repo и worktrees read-only, показывает найденные uncommitted files и checkpoint commit, отделяет факты от неизвестного. Возвращает `RECOVERY_MAPPED` с отдельным `target_status`; если provider target не подтверждён, не обобщает локальный `origin/main` до «main». Не создаёт branch, commit, push или PR/MR.

## Нельзя

Нельзя широко читать все большие JSONL по похожему title, угадывать repo по имени папки, менять pinned/archived state или трактовать просьбу «проверь» как разрешение на публикацию.
