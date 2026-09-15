# Анти-Пример: Несколько Repo И Неизвестный Target

## Вход

«В workspace пять child repos и два worktree с похожими файлами. Наверное, надо отправить всё в `origin/main`; сделай MR».

## Ожидаемое Поведение

Skill выполняет read-only recovery map, показывает candidate repos, commits, remotes и различия artifact scope. Поскольку настоящий target project не доказан, завершает `BLOCKED_TARGET_UNKNOWN` и просит точный repo URL или `owner/name`. После выбора повторно проверяет target branch и только тогда создаёт clean branch.

## Нельзя

Нельзя выбирать repo по похожему имени, считать `origin` upstream-ом, создавать branch во всех candidates, смешивать child repos или удалять старые worktrees ради упрощения карты.
