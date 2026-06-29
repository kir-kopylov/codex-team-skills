# Хороший Пример

## Вход

«PR уже смержен. Что теперь в рабочем дереве и можно ли убрать ветки?»

## Ожидаемое Поведение

Codex выполняет `fetch --all --prune`, проверяет PR `MERGED`, merge commit и reachability из `origin/main`. Если worktree clean, переключается на `main`, fast-forward'ит локальный `main` до `origin/main`, удаляет только локальные ветки, которые `git branch --merged origin/main` доказывает как merged. Старую ветку с rebased/superseded commit удаляет только после проверки, что смысл commit уже присутствует в `main`.

## Нельзя

Нельзя продолжать новую работу из смерженной feature branch. Нельзя удалять ветку только потому, что её remote `[gone]`. Нельзя говорить «repo чистый», если чистое только рабочее дерево, но активная ветка всё ещё feature branch.
