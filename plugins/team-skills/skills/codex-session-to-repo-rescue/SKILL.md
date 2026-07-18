---
name: codex-session-to-repo-rescue
description: >-
  Используйте этот skill, когда полезная работа осталась в длинной, зависшей или
  архивной Codex-сессии и нужно доказуемо перенести её в правильный repo и target
  branch: найти session file, cwd, worktree, commit и remote; отделить готовые
  артефакты от raw chat и локального служебного состояния; собрать clean PR/MR;
  проверить manifest, хэши, Git blobs и свежий checkout; доказать попадание
  результата в настоящий target. Срабатывает на фразы «сохрани результат длинной
  Codex-сессии в repo», «архивируй Codex-task, но сначала сохрани её repo-результат», «найди, куда сессия
  записала файлы», «перенеси результат сессии в чистый MR», «проверь, попала ли
  работа из сессии в main».
---

# Codex Session To Repo Rescue

## Согласие На Запуск

Явный вызов — slash-команда, имя skill или первая фраза из каталога — выполняйте сразу, без вопроса. При автосрабатывании на смысловое сходство сначала спросите одной строкой: «Задача похожа на team skill `codex-session-to-repo-rescue` — сохраняет результат длинной или архивной Codex-сессии в целевом repo через доказуемый clean PR/MR. Применить или решить без него?» — и ждите ответа. При отказе выйдите из skill молча: решите задачу с нуля и больше не упоминайте skill.

## Обзор

Восстанавливайте не текст разговора, а долговечный результат работы: файлы, commit, branch, worktree, evidence package и их связь с целевым remote. Стройте цепочку:

```text
Codex task -> session file -> cwd -> repo/worktree -> commit/files -> remote -> PR/MR -> target branch
```

Начинайте раньше обычного git-workflow: repo, worktree и commit могут быть неизвестны. Когда они доказаны, используйте `git-worktree-reality-check` как нижний read-only gate, а `git-pr-lifecycle-safeguard` — для clean branch, PR/MR и cleanup. Если известны repo и SHA/WIP и восстанавливать след Codex-сессии не нужно, сразу передавайте задачу этим git-skills.

## Режим И Полномочия

Сначала зафиксируйте режим по формулировке пользователя:

- `map-only` — найти и описать сохранённую работу; не менять repo, session state, branches или remotes;
- `prepare` — собрать и проверить clean package локально; не push и не открывать PR/MR;
- `publish` — commit, push и PR/MR входят в scope, только если пользователь просит добавить результат в repo, опубликовать или довести до PR/MR;
- `prove-target` — проверить уже созданный PR/MR или target branch без новой публикации.

Архивирование, удаление task/session, удаление checkpoint, branch или worktree не выводите из слова «сохранить». Для этих действий нужно отдельное явное намерение, а удаление checkpoint разрешайте только после доказательства результата в target.

## Процесс

### 1. Прочитать Known Exceptions

Перед выполнением прочитайте `known-exceptions.yaml`. Применяйте подходящее `do_next_time` сразу, не повторяя уже известную ошибку.

### 2. Идентифицировать Task Без Загрузки Всего Чата

1. Если доступен Codex thread/task tool, получите по нему `thread_id`, title, archived/pinned state и последние нужные метаданные.
2. До inventory создайте immutable target lock. Если дано только название task, добавьте наблюдаемый размер из UI; resolver использует index и только ранние user messages, а не широкое чтение raw chat:

   ```bash
   python3 <skill-dir>/scripts/rescue_evidence.py resolve-session \
     --title "<точное название>" --expected-size-mib <size> \
     --lock-file <run-dir>/target-lock.json
   ```

   `<run-dir>` должен быть приватным локальным каталогом вне любого Git worktree. `target-lock.json` содержит локальную identity и абсолютный session path: никогда не добавляйте его в manifest, commit или publish package.

   Если native task tool уже вернул точный ID, используйте `--thread-id <id>` вместо `--title`. Статус `identity_incomplete`, `ambiguous_target` или `target_not_found` — жёсткий стоп; не выбирайте первый или самый похожий candidate.
3. Продолжайте только после JSON-статуса `target_locked`. Inventory принимает lock, а не свободный `thread_id`:

   ```bash
   python3 <skill-dir>/scripts/rescue_evidence.py inventory-session \
     --target-lock <run-dir>/target-lock.json
   ```

4. Не заменяйте существующий lock другим target. `target_lock_conflict` означает, что текущий recovery run и все его выводы нужно явно аннулировать; для другого target создайте новый run-dir и новый lock.
5. Считайте подтверждёнными только поля, которые вернули текущие tools или файл: session path, `cwd`, archive state, repo root, worktrees, branch, HEAD и очищенные remotes.
6. Если inventory вернул `records_truncated=true`, `path_hints_truncated=true` или `discovery_status=partial`, не делайте отрицательный вывод «worktree/commit не найден». Повторите с большим `--max-records` или сузьте поиск дополнительным evidence.
7. Не считайте размер session-файла доказательством причины тормозов. Размер здесь только identity gate; performance triage — отдельная задача.

Если task tool недоступен, schema JSONL неизвестна или `thread_id` не найден, сообщите точный пробел. Не придумывайте связь с repo по похожему имени папки.

### 3. Построить Recovery Map

Для каждого кандидата соберите read-only evidence:

- session file и активный/архивный каталог;
- `cwd` из session metadata;
- repo root и `git worktree list --porcelain`;
- branch, upstream, HEAD, staged/unstaged/untracked и stash;
- commits, которых нет в предполагаемом target;
- changed paths и уже существующие durable artifacts;
- remote names и URL без credentials, query tokens и fragments;
- открытый PR/MR, если он есть.

Сначала ищите уже созданные файлы, commit и worktree. Raw session используйте только как указатель на действия, если durable artifacts не дают ответа. Не пересобирайте результат из длинного чата, пока не доказано, что файлов или commit нет.

### 4. Доказать Настоящий Target

Не считайте `origin/main` настоящим target автоматически.

Проверьте:

- какой repo должен владеть результатом;
- fork это или upstream;
- remote URL и default branch;
- base/target project и branch у PR/MR;
- source/head project, branch и commit;
- есть ли несколько child repos или worktrees с похожими артефактами.

Если остаются несколько равноправных target-кандидатов, завершите read-only карту со статусом `BLOCKED_TARGET_UNKNOWN` и попросите точный repo URL или `owner/name`. Не создавайте branch до выбора target.

Не пишите без уточнения «работы нет в main». Пока base/target project и branch не подтверждены provider metadata, допустима только точная формулировка: «результат не найден в проверенном `<remote>/<branch>`; настоящий target не подтверждён». В режиме `map-only` можно завершить `RECOVERY_MAPPED` с полем `target_status=unconfirmed`; этот статус не разрешает publish или cleanup.

Подробные provider checks и manifest contract читайте в `references/domain-playbook.md`.

### 5. Зафиксировать Artifact Allowlist

Составьте явный список полезных repo-relative paths и источник каждого пути: working tree, index, commit или approved artifact directory.

Никогда не включайте по умолчанию:

- Codex session JSONL, state/log SQLite и raw chat exports;
- `.codex/**`, `.goal-runtime/**`, hooks, active-goal state и локальные настройки;
- `.env*`, credentials, tokens, auth caches и credential-bearing remote URLs;
- raw exception logs, temporary files, private screenshots и личные абсолютные пути.

Если старая branch смешивает нужную работу с предыдущей историей, не сливайте её целиком. Создайте clean branch от доказанного target tip и перенесите только allowlist через `cherry-pick --no-commit`, точечный restore или копирование выбранных артефактов. Сохраните исходную branch/worktree как checkpoint.

### 6. Проверить Пакет До Commit

Минимальные проверки:

```bash
git diff --cached --check
git diff --cached --name-status
git diff --cached --stat
```

Дополнительно:

- сверить changed paths с allowlist и denylist;
- прогнать secret scan и repo tests;
- распарсить JSON, JSONL, YAML и другие структурированные файлы;
- проверить отсутствие conflict markers и случайных служебных файлов;
- если есть approved manifest — проверить `path`, `sha256` и `size` по нужным byte sources.

До commit проверяйте working tree и index:

```bash
python3 <skill-dir>/scripts/rescue_evidence.py verify-manifest \
  --repo <repo> --manifest <manifest.json> --sources working,index
```

После commit проверяйте commit и независимый fresh checkout:

```bash
python3 <skill-dir>/scripts/rescue_evidence.py verify-manifest \
  --repo <repo> --manifest <manifest.json> --sources commit,checkout --commit HEAD
```

Без `--exact-scope` команда проверяет только перечисленные manifest entries и возвращает `package_ready=false`: это допустимо для approved evidence subset, но не доказывает отсутствие лишних paths. Если manifest описывает полный artifact allowlist, до commit добавьте `--exact-scope index --base <target-tip>` вместе с byte source `index`, а после commit — `--exact-scope commit --base <target-tip>` вместе с source `commit`. Script сначала разрешает недоверенные revisions в commit OID, читает Git paths через NUL и запрещает зелёный scope при unmerged (`U`) или type-change (`T`) paths. Только `status=ok`, `hash_status=ok`, `scope.status=ok` и `package_ready=true` разрешают считать manifest-пакет полностью проверенным.

Если Windows working copy отличается от Git blob из-за EOL, не переписывайте approved evidence. Сначала докажите источник расхождения. При необходимости добавьте узкую `.gitattributes` policy, затем повторите проверку index, commit и fresh checkout.

### 7. Publish И Provider Reality Check

В режиме `publish`:

1. Создайте осмысленный commit только из allowlist.
2. Push выполните в feature branch, не в target branch.
3. Откройте PR/MR по языковой и governance policy целевого repo.
4. Сверьте changed files PR/MR с локальным allowlist.
5. Проверьте CI/checks, head/source commit и фактический target project/branch.
6. Не приписывайте себе merge, auto-merge или удаление source branch, если это наблюдаемое действие Git provider.

Если provider автоматически merged PR/MR, зафиксируйте это отдельно как внешний факт и продолжите с проверкой target. Если source branch уже автоматически удалена, не считайте ошибку повторного delete провалом cleanup.

### 8. Доказать Результат В Target

После merge или заявления «уже в main» обновите refs и проверьте минимум два независимых признака:

- target branch указывает на provider-confirmed target SHA;
- package commit reachable из target, либо squash/merge commit доказан provider metadata;
- diff выбранных paths между package commit и target равен нулю;
- manifest/hash/size воспроизводятся из target commit и fresh checkout;
- PR/MR head/source ref соответствует проверенному package commit.

Статус `TARGET_PROVEN` допустим только после этой проверки. Green CI, HTTP `200`, существующая remote branch или закрытый PR/MR сами по себе недостаточны.

### 9. Cleanup И Передача Ответственности

До `TARGET_PROVEN` сохраняйте:

- исходную архивную task/session;
- старую checkpoint branch/worktree;
- clean publish commit и manifest.

После `TARGET_PROVEN` удаляйте только новые временные worktrees/branches, если это входит в scope. Старый checkpoint не удаляйте автоматически: назовите его состояние и предложите отдельное решение.

В финале явно укажите:

- что уже сохранено и где;
- что доказано в target;
- что осталось резервом;
- что не публиковалось;
- какие CI/merge/cleanup действия выполнил provider;
- что остаётся за Codex и требуется ли действие пользователя.

## Статусы Завершения

- `RECOVERY_MAPPED` — цепочка до файлов/commit построена, mutations не выполнялись; отдельно указать `target_status=confirmed|unconfirmed`;
- `READY_TO_PUBLISH` — clean package локально проверен, но publish не входит в scope;
- `PUBLISHED_AWAITING_TARGET_PROOF` — PR/MR открыт или merged-state ещё не подтверждён;
- `TARGET_PROVEN` — результат доказан в настоящем target;
- `BLOCKED_TARGET_UNKNOWN` — несколько target-кандидатов, нужен точный repo;
- `BLOCKED_UNSAFE_SCOPE` — allowlist нельзя отделить от raw/private/local state без решения пользователя.

## Границы

Не используйте skill:

- для известного repo и известного WIP/SHA без session-forensics — используйте `git-pr-lifecycle-safeguard`;
- для простого вопроса «что в worktree?» — используйте `git-worktree-reality-check`;
- для создания skill из разговора — используйте `skill-methodologist`, затем `add-team-skill`;
- для диагностики тормозов Codex Desktop без задачи сохранить repo-результат;
- для восстановления удалённого текста чата как архива переписки;
- для force-push, history rewrite, destructive cleanup или удаления session/checkpoint без отдельного явного решения.

## Опрос После Использования

Опрос задаётся один раз — после `TARGET_PROVEN`, сдачи read-only recovery map или явного стопа, не посреди recovery/publish цикла. Если пользователь уже ответил «пропустить» в этой сессии, не переспрашивайте.

```text
Опрос по skill:
1. Что в этом использовании codex-session-to-repo-rescue было полезно?
2. Что стоит доработать в skill или его формате?
Можно ответить коротко или написать "пропустить".
```

Если пользователь ответил, сохраните санированную карточку в `~/.codex/skill-runs/codex-session-to-repo-rescue/usage-feedback.jsonl` — лучше через bundled script:

```bash
python3 scripts/log_usage_feedback.py --liked "..." --improve "..." --outcome "..."
```

Script перед записью редактирует приватные пути, контакты и token-like строки и сохраняет в JSONL `redaction_applied` и `redaction_types`. Если запись невозможна из-за sandbox, прав или отсутствия tools, не делайте вид, что лог сохранён: скажите об этом и покажите короткую JSONL-карточку для ручного сохранения. Raw-ответы, контакты, пути и секреты не коммитить.

## Логирование Сбоев

Перед выполнением прочитайте локальный `known-exceptions.yaml` как список уже известных случаев и применяйте подходящее `do_next_time` без нового поиска.

Если пользователь поправил skill, tool/API/browser упал, нарушен режим работы, пришлось искать workaround или skill сделал ложное предположение, запишите приватную карточку в `~/.codex/skill-runs/codex-session-to-repo-rescue/exception-log.jsonl`.

Пишите факты: что skill хотел сделать, что сделал, где сломался, какая предпосылка была ложной и что сделать в следующий раз. Если поле неизвестно, пишите `unknown`. Raw logs не коммитить.
