# Domain Playbook

## Что Нельзя Потерять

- точный `thread_id`, а не только изменяемый title task;
- различие активного и архивного session file;
- `cwd`, timestamp и другие метаданные только из наблюдаемого session record;
- repo root, git common dir, worktree path, branch, HEAD и upstream;
- artifact allowlist и provenance каждого path: working tree, index, commit или approved directory;
- source/head и base/target project, branch и commit у PR/MR;
- manifest `path + sha256 + size` и конкретный byte source проверки;
- checkpoint до доказательства результата в target;
- различие действия Codex и автоматического действия Git provider.

## Что Надо Обезличить

- имена пользователей в домашних каталогах и другие личные absolute paths;
- session titles и raw messages с клиентским контекстом;
- credentials, PAT, query tokens, URL fragments и auth-cache contents;
- account handles, private project IDs и внутренние hostnames, если skill публикуется;
- raw session JSONL, state/log SQLite, screenshots и exception logs;
- реальные commits, branch names и filenames в examples, если они раскрывают частный проект.

Runtime output может содержать локальные paths, необходимые текущему пользователю. В repo skill храните только synthetic values и общую механику.

## Interface Mechanics

### Codex Task И Session Storage

Предпочитайте task/thread tools для title, `thread_id`, archive и pinned state. Session JSONL используйте как read-only fallback и читайте потоково. Не загружайте длинный файл целиком ради `session_meta`.

CLI работает в два обязательных шага. Сначала `resolve-session` принимает либо точный `--thread-id` из native task/thread tool, либо точный `--title` вместе с `--expected-size-mib`/`--expected-bytes`. Название из `session_index.jsonl` имеет приоритет; fallback по раннему user message допустим только при отсутствии индексного названия и требует полного нормализованного совпадения. Неполная identity даёт `identity_incomplete`, несколько кандидатов — `ambiguous_target`, а повреждённые соседние JSONL перечисляются отдельно в `inspection_errors` и не могут стать target.

Успешный resolution создаёт immutable `target-lock.json` только в приватном локальном run-dir вне Git worktree. Lock содержит локальную identity и absolute session path, поэтому его запрещено включать в manifest, commit или publish package. Существующий lock переиспользуется только для того же `thread_id + session_file + archive state`; попытка переключения возвращает `target_lock_conflict` и требует аннулировать прежний recovery run. Во втором шаге `inventory-session --target-lock <path>` читает только зафиксированную цель; свободный `--thread-id` этот subcommand не принимает.

`inventory-session` извлекает ограниченное число records, по умолчанию 10 000, и отклоняет неположительный `--max-records`. Он учитывает, что tool arguments могут лежать не только как JSON в `arguments`, но и как JavaScript-like строка в `input`; из неё извлекаются только `cwd`, `workdir` и существующие absolute path hints. Неизвестную schema CLI возвращает как `schema_unconfirmed`, а не интерпретирует догадкой. Git repos внутри `<CODEX_HOME>` не включаются в artifact candidates. `records_truncated`, `path_hints_truncated` или `discovery_status=partial` запрещают отрицательный вывод о ненайденном worktree.

### Git И Worktrees

Для найденного `cwd` используйте `git rev-parse --show-toplevel` и `git worktree list --porcelain`. Git worktree может лежать вне repo root, а workspace root может быть контейнером child repos. Не сокращайте эту карту до ближайшей папки с `.git`.

Remote URL выводите без userinfo, password, query и fragment. Перед mutation используйте нижний gate `git-worktree-reality-check`.

### Provider Target Proof

Для GitLab сверяйте `target_project`, `target_branch`, `source_project`, `source_branch`, head/diff refs и после merge — `merge_commit_sha` или `squash_commit_sha`. MR refs вроде `refs/merge-requests/<iid>/head` полезны как дополнительный признак, но доступность ref зависит от server и fetch policy.

Для GitHub сверяйте base repository/branch, head repository/branch/SHA, merged state и merge commit или squash commit. Ни имя `origin`, ни URL открытого PR/MR сами по себе не доказывают target.

После merge fetch target branch и докажите reachability package commit либо совпадение выбранных paths/hashes с provider-confirmed target SHA. Без provider-confirmed base/target запрещено обобщать локальную проверку `origin/main` до фразы «работы нет в main».

### Evidence Manifest

Используйте JSON contract:

```json
{
  "version": 1,
  "files": [
    {
      "path": "docs/evidence/decision.md",
      "sha256": "64 lowercase hex characters",
      "size": 1234
    }
  ]
}
```

`path` всегда repo-relative POSIX path без `..`, backslash и local-state prefixes. Manifest entries должны быть уникальны. `verify-manifest` проверяет заявленные sources независимо:

- `working` — bytes текущего filesystem checkout;
- `index` — staged Git blob;
- `commit` — blob из указанного commit;
- `checkout` — bytes независимого fresh local clone после checkout commit.

До commit обычно используйте `working,index`; после commit — `commit,checkout`. Если задача требует идентичности всех четырёх, заявите все sources явно. Без `--exact-scope` это только проверка перечисленных entries: `package_ready=false`. Для manifest полного publish allowlist используйте `--exact-scope index --base <target-tip>` с source `index` до commit и `--exact-scope commit --base <target-tip>` с source `commit` после commit. Лишний, удалённый, отсутствующий, unmerged (`U`) или type-change (`T`) path должен дать `scope.status=mismatch`; `--base` и `--commit` должны сначала разрешиться в commit OID.

## Recovery And Edge Cases

- Session file найден, но `cwd` отсутствует: вернуть session evidence и `cwd_status=unknown`; не угадывать repo.
- `cwd` больше не существует: искать worktree/commit только по дополнительным наблюдаемым clues; не сканировать весь диск без scope.
- Несколько session files удовлетворяют зафиксированной identity: вернуть `ambiguous_target` до создания lock; не выбирать молча.
- Существующий target lock не совпадает с новым кандидатом: вернуть `target_lock_conflict`, сохранить `active_target` и не публиковать отклонённый кандидат как текущий `target`.
- Dirty candidate worktree: ничего не stash/pop автоматически; отделить чужой WIP и вызвать git reality check.
- Branch history mixed: clean branch от target tip плюс explicit allowlist; исходный checkpoint сохранить.
- Manifest совпадает в index, но не working/checkout: проверить EOL/filter policy, не обновлять approved hashes от изменённых bytes.
- PR/MR auto-merged или source branch auto-deleted: зафиксировать provider action, затем доказать target; повторный delete не нужен.
- PR/MR closed без merge: работа не в target; сохранить package commit и вернуть `PUBLISHED_AWAITING_TARGET_PROOF` или явный blocked state.
