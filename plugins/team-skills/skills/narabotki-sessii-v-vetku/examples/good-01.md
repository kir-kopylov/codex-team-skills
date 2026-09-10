# Хороший Пример: Архивная Task И Смешанный Checkpoint

## Вход

«После архивации длинной Codex-сессии приложение стало быстрее. В той task был готов пакет документов. Найди его, исключи служебные файлы и добавь результат в целевой GitLab repo через чистый MR».

## Ожидаемое Поведение

Skill разрешает title в `thread_id`, находит archived session file и `cwd`, затем строит карту worktree/branch/commit/remotes. Обнаруживает checkpoint commit с 47 полезными файлами и двумя локальными служебными файлами. Доказывает target project/branch, создаёт clean branch от target tip, применяет checkpoint через `cherry-pick --no-commit`, исключает `.codex/**` и `.goal-runtime/**`, проверяет allowlist, форматы, secrets и manifest. После push/MR сверяет provider target, head ref и changed files. Если provider сам выполняет merge и удаляет source branch, фиксирует это как внешний факт. Завершает только после `TARGET_PROVEN`, сохраняя исходный checkpoint и archived task резервом.

## Нельзя

Нельзя merge старую branch целиком, коммитить raw session JSONL, считать `origin/main` настоящим target без проверки или удалять checkpoint до доказательства результата в target.
