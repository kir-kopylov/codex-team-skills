# Хороший Пример

## Вход

«Есть старый локальный commit `469c9fe` с новым skill. Его нет в remote и PR. Сохрани его: вынеси в чистую ветку от `origin/main`, прогони тесты и открой отдельный PR.»

## Ожидаемое Поведение

Codex сначала выполняет read-only проверку target repo: status, branch, diff, stash, upstream, reachability commit. Затем создаёт новую ветку от актуального `origin/main`, делает `cherry-pick 469c9fe`, разрешает конфликты без потери текущих строк `catalog.md`, доводит пакет до текущего repo contract, запускает `git diff --check` и `python3 -m pytest`, пушит ветку и открывает draft PR. Если после merge другого PR ветка стала conflict, Codex делает rebase на свежий `origin/main` и обновляет remote через `--force-with-lease`.

## Нельзя

Нельзя cherry-pick'ить старый commit поверх случайной текущей feature branch. Нельзя игнорировать упавшие тесты. Нельзя force-push без `--force-with-lease`. Нельзя терять уже существующие строки каталога при разрешении конфликта.
