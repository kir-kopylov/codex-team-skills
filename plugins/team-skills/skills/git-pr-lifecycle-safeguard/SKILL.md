---
name: git-pr-lifecycle-safeguard
description: Используйте этот skill, когда нужно безопасно провести локальный WIP или старый commit через цикл clean branch, tests, draft PR, mergeable check и cleanup после merge, либо когда есть риск смешать dirty tree, старую ветку, stale remote branch, merged PR или чужие изменения. Skill сначала выполняет read-only reality check, затем действует только по доказанному scope.
---

# Git PR Lifecycle Safeguard

## Согласие На Запуск

Явный вызов — slash-команда, имя skill или первая фраза из каталога — выполняйте сразу, без вопроса. При автосрабатывании на смысловое сходство сначала спросите одной строкой: «Задача похожа на team skill `git-pr-lifecycle-safeguard` — безопасно проводит WIP или старый commit через clean PR и post-merge cleanup. Применить или решить без него?» — и ждите ответа. При отказе выйдите из skill молча: решите задачу с нуля и больше не упоминайте skill.

## Обзор

Skill защищает цикл `WIP/old commit -> clean PR -> merge -> branch cleanup`. Он нужен не для любого git-вопроса, а когда есть риск смешать состояния: dirty tree, старый локальный commit, неправильная feature branch, stale remote branch, PR после merge, branch cleanup или remote branch clutter.

Главный принцип: сначала доказать реальное состояние через read-only проверку, затем менять repo только по явному и проверенному scope.

## Естественные Входы

Запускайте skill на фразы:

- «вынеси это в отдельную ветку»;
- «сохрани старый commit»;
- «сделай PR, но не смешивай»;
- «этот WIP не должен попасть в текущую ветку»;
- «PR смержен, что теперь?»;
- «убери branch clutter»;
- «можно архивировать после PR?»;
- «почисти remote branches»;
- «доведи локальную работу до clean PR»;
- «после merge верни repo в чистое состояние».

## Общий Первый Шаг

Перед любым изменяющим действием выполните read-only reality check. Если доступен `git-worktree-reality-check`, используйте его правила как нижний gate.

Минимальный снимок:

```bash
git -C <repo> status --short --branch --untracked-files=all
git -C <repo> diff --stat
git -C <repo> diff --cached --stat
git -C <repo> stash list --max-count=5
git -C <repo> branch -vv
```

Если работа касается push, PR, merge или remote cleanup, после локального снимка обновите refs и проверьте PR state:

```bash
git -C <repo> fetch --all --prune
git -C <repo> branch -r --merged origin/main
git -C <repo> branch -r --no-merged origin/main
```

Не называйте repo «чистым», если чистое только рабочее дерево, но активная ветка не та, upstream `[gone]`, есть локальный commit без PR или осталась remote branch с diff относительно `origin/main`.

## Режим 1: local-wip-to-clean-pr

Используйте, когда локальный WIP или старый commit нужно вынести в отдельный PR без смешения с текущей веткой.

Процесс:

1. Зафиксируйте исходный scope:
   - текущая ветка и upstream;
   - staged, unstaged, untracked;
   - нужные файлы или commit SHA;
   - есть ли чужие изменения в рабочем дереве.
2. Если есть WIP в текущем дереве, сохраните его безопасно:
   - `git stash push --include-untracked -m "<описание>"`, если нужно перенести весь WIP;
   - явный `git add <paths>` только после проверки scope, если пользователь подтвердил файлы;
   - не используйте `git add .` при mixed worktree.
3. Создайте clean branch от актуального `origin/main`:
   - `git switch -c codex/<short-name> origin/main`;
   - для старого commit используйте `git cherry-pick <sha>`.
4. Разрешайте конфликты без потери текущих строк:
   - для `catalog.md` сохраняйте уже существующие skill rows и добавляйте новую строку рядом;
   - для registry/docs не откатывайте изменения, пришедшие в `origin/main`;
   - после ручного разрешения проверяйте отсутствие стандартных conflict-marker строк.
5. Доведите пакет до текущего repo contract:
   - `known-exceptions.yaml`;
   - секция `## Логирование Сбоев`;
   - examples и catalog row для `team-ready`;
   - отсутствие шаблонных заглушек.
6. Запустите проверки:
   - `git diff --check`;
   - релевантный test command, обычно `python3 -m pytest`.
7. Сформируйте один понятный commit или объясните, почему нужно несколько.
8. Push:
   - обычный `git push -u origin <branch>`;
   - после rebase или amend только `git push --force-with-lease`.
9. Откройте PR - это стандартное завершение цикла `local-wip-to-clean-pr`, а не
   шаг, ожидающий отдельного запроса на публикацию:
   - title и body должны описывать scope, происхождение WIP и проверки;
   - затем проверьте `mergeable`, changed files и checks.
10. После открытия или обновления PR проверьте автоматическое review от
    `chatgpt-codex-connector`: если согласны с замечанием - почините и
    запушьте фикс; если не согласны или видите иначе - ответьте на
    комментарий с обоснованием на русском. Не оставляйте замечание бота без
    ответа ни в одну, ни в другую сторону. Это про обработку уже пришедшего
    отзыва, а не про подмену собственного review содержимого PR.

## Режим 2: post-merge-branch-housekeeping

Используйте после merge или когда пользователь хочет убрать branch clutter.

Процесс:

1. Обновите refs:
   - `git fetch --all --prune`.
2. Проверьте, что PR действительно merged, а не только green:
   - PR `state`;
   - `mergedAt` или merge commit;
   - commit reachable из `origin/main`.
3. Верните локальный repo в ожидаемое состояние:
   - если worktree clean, переключитесь на `main`;
   - fast-forward local `main` до `origin/main`;
   - не продолжайте новую работу из старой feature branch.
4. Удалите локальные branches только если они merged в `origin/main`.
5. Для remote cleanup:
   - перечислите `git branch -r --merged origin/main`;
   - сверяйте с PR state, если branch name неочевиден;
   - удаляйте remote branch только если она доказанно merged или явно признана stale/discarded пользователем.
6. Unmerged remote branches не удаляйте автоматически:
   - покажите commit, diff, возраст, PR state;
   - классифицируйте `keep`, `delete after confirmation`, `rebuild as new PR`.
7. В конце покажите:
   - текущую ветку;
   - clean worktree;
   - локальные branches;
   - remote branches, которые остались, и почему.

## Правила Безопасности

Нельзя:

- использовать `git add .` при mixed worktree;
- удалять ветку, если commit не reachable из `origin/main` или merged PR;
- force-push без `--force-with-lease`;
- выполнять `git reset --hard`;
- считать `git branch -r` достаточным доказательством для удаления remote branch;
- продолжать новую работу из старой feature branch после merge;
- считать skipped publish job проблемой без проверки условия workflow;
- считать `200`, green check или merged PR доказательством локальной установки.

## Границы

Не используйте skill:

- для учебного вопроса без намерения менять repo;
- для CI-debug как отдельной задачи, если проблема уже локализована в логах GitHub Actions;
- для публикации PR, если пользователь просил только анализ или план;
- для destructive cleanup вне подтверждённого repo;
- чтобы заменить review содержимого PR.

Если есть несколько repo-кандидатов или пользователь не указал target repo, остановитесь после read-only поиска и попросите выбрать один repo.

## Логирование Сбоев

Перед выполнением прочитайте локальный `known-exceptions.yaml` как список уже известных случаев и применяйте подходящее `do_next_time` без нового поиска.

Если пользователь поправил skill, tool/API/browser упал, нарушен режим работы, пришлось искать workaround или skill сделал ложное предположение, запишите приватную карточку в `~/.codex/skill-runs/<skill-name>/exception-log.jsonl`.

Пишите факты: что skill хотел сделать, что сделал, где сломался, какая предпосылка была ложной и что сделать в следующий раз. Если поле неизвестно, пишите `unknown`. Raw logs не коммитить.

## Критерий Готовности

Работа завершена, когда:

- рабочее дерево clean или явно назван оставшийся intentional WIP;
- текущая ветка соответствует этапу: clean PR branch до merge, `main` после cleanup;
- PR создан или cleanup завершён;
- проверки названы явно;
- merged local branches удалены;
- remote branches удалены только если merged/closed и safe;
- оставшиеся unmerged branches перечислены с причиной keep/delete-later;
- пользователь понимает, что не было изменено и почему.
