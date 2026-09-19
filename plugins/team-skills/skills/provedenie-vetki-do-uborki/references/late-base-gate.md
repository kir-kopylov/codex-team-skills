# Поздний Гейт Базы И Recovery-Stash

Читайте этот reference, когда `origin/main` изменился после тестов либо перед
push. Сначала выберите один из двух потоков. Не переносите правила WIP на
чистую ветку и не маскируйте dirty tree под чистый committed-only поток.

## Общие Доказательства

До тестов сохраните:

- `tested_base_sha` — текущий `origin/main`;
- полный `git status --porcelain=v1 --untracked-files=all`, включая untracked;
- точный список intended paths;
- `tested_tree=$(git -C "$repo" write-tree)` после явного staging intended
  scope и проверки, что нет unstaged и untracked файлов.

До разделения потоков получите текущую ветку. Она нужна и clean-переносу, и
идентичности recovery-stash; пустой detached `HEAD` закрывает автоматическое
продолжение до любой Git-mutation:

```bash
if ! branch=$(git -C "$repo" branch --show-current); then
  branch=
  exit 1
fi
if ! test -n "$branch"; then
  exit 1
fi
```

Тесты относятся только к `tested_tree`.

## После Каждого Test Run

Сразу после каждого первоначального или повторного test run, до commit,
выполните новый remote gate:

```bash
if ! git -C "$repo" fetch origin --prune; then
  exit 1
fi
if ! current_base_sha=$(git -C "$repo" rev-parse origin/main); then
  current_base_sha=
  exit 1
fi
if ! test "$current_base_sha" = "$tested_base_sha"; then
  exit 1
fi
if ! git -C "$repo" merge-base --is-ancestor "$current_base_sha" HEAD; then
  exit 1
fi
verified_base_sha="$current_base_sha"
```

`verified_base_sha` появляется только после успешных compare и ancestry и
обязательно до commit. Каждый producer и compare закрывается собственным
переходом; гейт не полагается на `errexit` или статус последней команды. Если
любое условие не прошло, результаты test run
устарели: перенесите работу, заново установите `tested_base_sha` и
`tested_tree`, повторите проверки, а затем снова выполните весь этот gate.

После drift эффективного изменения Codex plugin отдельно прочитайте semver из
нового `origin/main` и пересчитайте версию
`plugins/team-skills/.codex-plugin/plugin.json` относительно этой базы до
нового `tested_tree` и повторного test run. Общего «обновить metadata» здесь
недостаточно.

## Непосредственно Перед Commit

После remote gate и без изменений между ним и commit докажите одновременно:

```bash
if ! current_index_tree=$(git -C "$repo" write-tree); then
  current_index_tree=
  exit 1
fi
if ! test "$current_index_tree" = "$tested_tree"; then
  exit 1
fi
if ! git -C "$repo" diff --quiet; then
  exit 1
fi
if ! untracked_paths=$(git -C "$repo" ls-files --others --exclude-standard); then
  untracked_paths=
  exit 1
fi
if ! test -z "$untracked_paths"; then
  exit 1
fi
if ! unmerged_entries=$(git -C "$repo" ls-files -u); then
  unmerged_entries=
  exit 1
fi
if ! test -z "$unmerged_entries"; then
  exit 1
fi
```

Первая команда связывает index с проверенным tree, вторая запрещает tracked
изменения вне index, третья — untracked, четвёртая — unmerged entries. Любой
неуспех запрещает commit и требует нового `tested_tree` и test run.

После commit сохраните `verified_head_sha=$(git -C "$repo" rev-parse HEAD)` и
проверьте:

```bash
if ! verified_head_sha=$(git -C "$repo" rev-parse HEAD); then
  verified_head_sha=
  exit 1
fi
if ! committed_tree_sha=$(
  git -C "$repo" rev-parse "$verified_head_sha^{tree}"
); then
  committed_tree_sha=
  exit 1
fi
if ! test "$committed_tree_sha" = "$tested_tree"; then
  exit 1
fi
if ! committed_status=$(
  git -C "$repo" status --porcelain=v1 --untracked-files=all
); then
  committed_status=
  exit 1
fi
if ! test -z "$committed_status"; then
  exit 1
fi
```

Несовпадение означает, что проверен не тот tree или commit содержит не тот
scope. Только этот compare доказывает, что `verified_head_sha` содержит ровно
`tested_tree`; иначе commit нельзя считать готовым к push.

## Поток A: Чистое Committed-Only Состояние

Выбирайте его, только если полный status пуст, а весь intended scope уже
находится в commit'ах ветки. Recovery-stash здесь не создаётся.

Если ветка уже опубликована, до rebase сохраните ожидаемый remote SHA:

```bash
if ! remote_branch_row=$(
  git -C "$repo" ls-remote --exit-code --heads origin "refs/heads/$branch"
); then
  remote_branch_row=
  exit 1
fi
if ! test -n "$remote_branch_row"; then
  exit 1
fi
case "$remote_branch_row" in
  (*$'\n'*) exit 1 ;;
esac
expected_remote_sha=${remote_branch_row%%$'\t'*}
expected_remote_ref=${remote_branch_row#*$'\t'}
if ! test "$expected_remote_ref" = "refs/heads/$branch"; then
  exit 1
fi
if ! [[ "$expected_remote_sha" =~ ^[0-9a-f]{40}([0-9a-f]{24})?$ ]]; then
  exit 1
fi
```

Сам перенос тоже закрывается до любых последующих проверок:

```bash
if ! git -C "$repo" rebase origin/main; then
  exit 1
fi
```

После успешного rebase повторите полную suite,
base-sensitive checks и затронутые живые пробы. После них обязательно снова
пройдите раздел «После Каждого Test Run»; только он устанавливает новый
`verified_base_sha`. Зафиксируйте новые `tested_tree` и `verified_head_sha`.
Если rebase или повторный remote gate остановился, не переходите к push.

## Поток B: WIP Через Recovery-Stash

Автоматический stash/rebase разрешён, только когда все staged, unstaged и
untracked пути из полного status доказанно входят в intended scope. Сравните
глобальный список с явными pathspec. Если есть хотя бы один чужой, неизвестный
или неразделимый путь, это mixed WIP: не создавайте stash, не запускайте rebase
и запросите один выбор точного состава патча. Равенства имён файлов
недостаточно: если один intended-файл содержит одновременно нужные и чужие
hunks, до общего staging должен быть доказан точный hunk scope. Неразделимые
same-path изменения тоже считаются mixed WIP и останавливают Git-mutation.

До первого `add -A` докажите точное равенство dirty path set и
`intended_paths`. Отдельный `hunk_scope_state` появляется только после read-only
сверки всех hunks; одно равенство путей его не устанавливает:

```bash
if ! initial_unmerged=$(git -C "$repo" ls-files -u); then
  initial_unmerged=
  exit 1
fi
if ! test -z "$initial_unmerged"; then
  exit 1
fi
set -o pipefail
if ! initial_path_scope_state=$(
  {
    git -C "$repo" diff --name-only -z || exit 1
    git -C "$repo" diff --cached --name-only -z || exit 1
    git -C "$repo" ls-files --others --exclude-standard -z || exit 1
  } | python3 -c '
import os, sys
intended_count = int(sys.argv[1])
intended = {os.fsencode(value) for value in sys.argv[2:]}
if len(sys.argv[2:]) != intended_count or len(intended) != intended_count:
    raise SystemExit(1)
rows = sys.stdin.buffer.read().split(b"\0")
if rows and rows[-1] == b"":
    rows.pop()
if any(not row for row in rows) or set(rows) != intended:
    raise SystemExit(1)
print("INTENDED_PATH_SCOPE_PASS")
' "${#intended_paths[@]}" "${intended_paths[@]}"
); then
  initial_path_scope_state=
  exit 1
fi
if ! test "$initial_path_scope_state" = INTENDED_PATH_SCOPE_PASS; then
  exit 1
fi
if ! test "${hunk_scope_state:-UNPROVEN}" = INTENDED_HUNKS_ONLY; then
  exit 1
fi
```

Для уже опубликованной WIP-ветки до первой mutation прочитайте ожидаемый lease
не из локального tracking ref, а напрямую с проверяемого remote. Ограниченный
`remote.origin.fetch` может обновлять только `main`; такой fetch не доказывает
head feature-ветки:

```bash
if ! remote_branch_row=$(
  git -C "$repo" ls-remote --exit-code --heads origin "refs/heads/$branch"
); then
  remote_branch_row=
  exit 1
fi
if ! test -n "$remote_branch_row"; then
  exit 1
fi
case "$remote_branch_row" in
  (*$'\n'*) exit 1 ;;
esac
expected_remote_sha=${remote_branch_row%%$'\t'*}
expected_remote_ref=${remote_branch_row#*$'\t'}
if ! test "$expected_remote_ref" = "refs/heads/$branch"; then
  exit 1
fi
if ! [[ "$expected_remote_sha" =~ ^[0-9a-f]{40}([0-9a-f]{24})?$ ]]; then
  exit 1
fi
```

До первой mutation отдельно классифицируйте scope. Любой intended path внутри
`plugins/team-skills/` означает эффективное изменение Codex plugin и требует,
чтобы manifest входил в `intended_paths`. Если таких путей нет, recovery-поток
не добавляет manifest и не запускает semver-гейт:

```bash
manifest_relative_path=plugins/team-skills/.codex-plugin/plugin.json
if ! plugin_scope_state=$(python3 -c '
import sys
manifest, *paths = sys.argv[1:]
plugin_paths = [path for path in paths if path.startswith("plugins/team-skills/")]
if not plugin_paths:
    print("NO_PLUGIN_CHANGE")
elif manifest not in paths:
    raise SystemExit(1)
else:
    print("PLUGIN_CHANGE")
' "$manifest_relative_path" "${intended_paths[@]}"); then
  plugin_scope_state=
  exit 1
fi
case "$plugin_scope_state" in
  PLUGIN_CHANGE|NO_PLUGIN_CHANGE) ;;
  *) exit 1 ;;
esac
```

Перед первым использованием `stable_paths` докажите, что это не выбранное
вручную подмножество. Стабильный scope обязан в точности равняться всему
`intended_paths` за вычетом manifest, и такое исключение разрешено только при
`plugin_scope_state=PLUGIN_CHANGE`. В `NO_PLUGIN_CHANGE` исключать нельзя ни
один intended path:

```bash
# STABLE_SCOPE_GATE_BEGIN
if ! stable_scope_state=$(python3 -c '
import os, sys
plugin_state = sys.argv[1]
manifest = os.fsencode(sys.argv[2])
stable_count = int(sys.argv[3])
intended_count = int(sys.argv[4])
values = [os.fsencode(value) for value in sys.argv[5:]]
if len(values) != stable_count + intended_count:
    raise SystemExit(1)
stable_values = values[:stable_count]
intended_values = values[stable_count:]
stable = set(stable_values)
intended = set(intended_values)
if len(stable) != stable_count or len(intended) != intended_count:
    raise SystemExit(1)
if plugin_state == "PLUGIN_CHANGE":
    if manifest not in intended:
        raise SystemExit(1)
    allowed_derived = {manifest}
elif plugin_state == "NO_PLUGIN_CHANGE":
    allowed_derived = set()
else:
    raise SystemExit(1)
if stable != intended - allowed_derived:
    raise SystemExit(1)
print("STABLE_SCOPE_PASS")
' "$plugin_scope_state" "$manifest_relative_path" \
  "${#stable_paths[@]}" "${#intended_paths[@]}" \
  "${stable_paths[@]}" "${intended_paths[@]}"); then
  stable_scope_state=
  exit 1
fi
if ! test "$stable_scope_state" = STABLE_SCOPE_PASS; then
  exit 1
fi
# STABLE_SCOPE_GATE_END
```

`STABLE_SCOPE_PASS` должен быть получен до `UNIQUE_HUNK_MAPPING_PASS`,
`stash apply` и построения `expected_tree`. Пропущенный stable path, лишнее
исключение либо попытка считать manifest derived-полем вне `PLUGIN_CHANGE`
останавливают recovery-поток; stash сохраняется.

### 1. Зафиксировать Точную Дельту И Создать Один Stash

До `stash push` полностью stage доказанный intended scope, включая additions,
deletions, untracked и изменения mode. Отдельно назовите base-derived поля,
которые после drift обязаны измениться по детерминированному правилу. Для этого
repo таким полем является только `version` в Codex plugin manifest, и только
при `plugin_scope_state=PLUGIN_CHANGE`. В этой ветке сохраните
исходную версию базы, intended-версию и доказанный `version_bump_kind`:
`patch`, `minor` или `major`, определённый по старой базе. После drift версия
должна стать следующим semver того же типа относительно нового `origin/main`.
Автоматически продолжайте, только если intended-версия точно равна следующему
semver этого типа относительно исходной базы: `patch` увеличивает третью часть,
`minor` — вторую и обнуляет третью, `major` — первую и обнуляет остальные.
Не заменяйте неизвестный или намеренный `minor`/`major` на `patch`: если тип
повышения нельзя доказать из patch scope и решения автора либо intended-версия
не является таким точным следующим semver, остановитесь для одного выбора.
Остальные пути и поля считаются стабильной WIP-дельтой.

Сохраните точное дерево staged WIP до stash. Оно связывает recovery-запись с
тем состоянием, которое было проверено на старой базе, но не используется для
прямого сравнения с новой базой: такой compare дал бы ложный mismatch при любом
новом base commit. В plugin-ветке для manifest отдельно сохраните fingerprint
канонического JSON без поля `version`; так его содержательная часть остаётся
проверяемой, а обязательный пересчёт версии не превращается в ложную потерю
WIP. Содержимое WIP и manifest не печатайте и не сохраняйте вне локальных Git
objects и hash:

```bash
if ! old_head_sha=$(git -C "$repo" rev-parse HEAD); then
  old_head_sha=
  exit 1
fi
if ! test -n "$old_head_sha"; then
  exit 1
fi
if ! git -C "$repo" add -A; then
  exit 1
fi
if ! unstaged_paths=$(git -C "$repo" diff --name-only); then
  unstaged_paths=
  exit 1
fi
if ! test -z "$unstaged_paths"; then
  exit 1
fi
if ! untracked_paths=$(git -C "$repo" ls-files --others --exclude-standard); then
  untracked_paths=
  exit 1
fi
if ! test -z "$untracked_paths"; then
  exit 1
fi
if ! intended_index_tree=$(git -C "$repo" write-tree); then
  intended_index_tree=
  exit 1
fi
if ! test -n "$intended_index_tree"; then
  exit 1
fi
if ! test "$intended_index_tree" = "$tested_tree"; then
  exit 1
fi
case "$plugin_scope_state" in
PLUGIN_CHANGE)
  if ! manifest_payload_fingerprint=$(
    python3 -c '
import hashlib, json, pathlib, sys
p = pathlib.Path(sys.argv[1])
d = json.loads(p.read_text(encoding="utf-8"))
d.pop("version", None)
payload = json.dumps(d, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
print(hashlib.sha256(payload.encode("utf-8")).hexdigest())
' "$repo/plugins/team-skills/.codex-plugin/plugin.json"
  ); then
    manifest_payload_fingerprint=
    exit 1
  fi
  if ! test -n "$manifest_payload_fingerprint"; then
    exit 1
  fi
  ;;
NO_PLUGIN_CHANGE)
  manifest_payload_fingerprint=NOT_REQUIRED
  ;;
*)
  exit 1
  ;;
esac
```

Для каждого присваивания сначала явно проверьте успешный exit status всей
команды или pipeline, затем непустоту значения. Одного `pipefail` и `test -n`
недостаточно: object ID частичного результата тоже может быть непустым.

После этого сохраните полный набор object SHA и subjects:

```bash
if ! stash_evidence_dir=$(mktemp -d); then
  stash_evidence_dir=
  exit 1
fi
if ! test -n "$stash_evidence_dir"; then
  exit 1
fi
stash_before_path="${stash_evidence_dir:?}/before"
stash_after_path="${stash_evidence_dir:?}/after"
stash_new_path="${stash_evidence_dir:?}/new"
if ! test ! -e "$stash_before_path"; then exit 1; fi
if ! test ! -e "$stash_after_path"; then exit 1; fi
if ! test ! -e "$stash_new_path"; then exit 1; fi
set -o pipefail
if ! git -C "$repo" stash list --format='%H' | LC_ALL=C sort \
  >"$stash_before_path"; then
  exit 1
fi
```

Задайте уникальное точное сообщение, основанное на текущей ветке, базе и уже
сохранённом исходном HEAD. Так как полный dirty set уже доказанно равен
intended scope, создайте общий stash без pathspec: это сохраняет в том числе
deletions, для которых path-scoped stash может завершиться ошибкой.

```bash
recovery_message="codex-recovery:${branch}:${tested_base_sha}:${old_head_sha}"
if ! git -C "$repo" stash push --include-untracked \
  -m "$recovery_message"; then
  exit 1
fi
if ! git -C "$repo" stash list --format='%H' | LC_ALL=C sort \
  >"$stash_after_path"; then
  exit 1
fi
if ! comm -13 "$stash_before_path" "$stash_after_path" >"$stash_new_path"; then
  exit 1
fi
if ! recovery_stash_count=$(wc -l <"$stash_new_path" | tr -d ' '); then
  recovery_stash_count=
  exit 1
fi
if ! test "$recovery_stash_count" = 1; then
  exit 1
fi
if ! recovery_stash_sha=$(sed -n '1p' "$stash_new_path"); then
  recovery_stash_sha=
  exit 1
fi
if ! test -n "$recovery_stash_sha"; then
  exit 1
fi
```

Сравните наборы до и после. Продолжайте только если появилось ровно одно новое
значение `%H`; его и сохраните как `recovery_stash_sha`. Не получайте его через
`stash@{0}`: успешный no-op `stash push` не создаёт запись и иначе может
присвоить старой записи чужое владение.

Проверьте точный subject новой записи:

```bash
expected_stash_subject="On ${branch}: ${recovery_message}"
if ! actual_stash_subject=$(
  git -C "$repo" show -s --format='%s' "$recovery_stash_sha"
); then
  actual_stash_subject=
  exit 1
fi
if ! test "$actual_stash_subject" = "$expected_stash_subject"; then
  exit 1
fi
if ! stash_base_sha=$(git -C "$repo" rev-parse "${recovery_stash_sha}^1"); then
  stash_base_sha=
  exit 1
fi
if ! stash_index_base_sha=$(
  git -C "$repo" rev-parse "${recovery_stash_sha}^2^1"
); then
  stash_index_base_sha=
  exit 1
fi
if ! stash_index_tree=$(
  git -C "$repo" rev-parse "${recovery_stash_sha}^2^{tree}"
); then
  stash_index_tree=
  exit 1
fi
if ! stash_worktree_tree=$(
  git -C "$repo" rev-parse "${recovery_stash_sha}^{tree}"
); then
  stash_worktree_tree=
  exit 1
fi
if ! test "$stash_base_sha" = "$old_head_sha"; then
  exit 1
fi
if ! test "$stash_index_base_sha" = "$old_head_sha"; then
  exit 1
fi
if ! test "$stash_index_tree" = "$intended_index_tree"; then
  exit 1
fi
if ! test "$stash_worktree_tree" = "$intended_index_tree"; then
  exit 1
fi
```

После stash полный status, включая untracked, обязан быть пуст:

```bash
if ! post_stash_status=$(
  git -C "$repo" status --porcelain=v1 --untracked-files=all
); then
  post_stash_status=
  exit 1
fi
if ! test -z "$post_stash_status"; then
  exit 1
fi
```

Если новая запись не доказана ровно одна, parent не равен исходному HEAD,
index/worktree tree stash не равны сохранённому `intended_index_tree`, subject
отличается или дерево не стало глобально чистым, rebase запрещён. Существующие
stashes не изменяйте.

### 2. Перенести И Проверить WIP

Только после глобальной проверки чистоты выполните rebase. До применения stash
сохраните новый HEAD:

```bash
if ! git -C "$repo" rebase origin/main; then
  exit 1
fi
if ! new_head_sha=$(git -C "$repo" rev-parse HEAD); then
  new_head_sha=
  exit 1
fi
if ! test -n "$new_head_sha"; then
  exit 1
fi
if ! tested_base_sha=$(git -C "$repo" rev-parse origin/main); then
  tested_base_sha=
  exit 1
fi
if ! git -C "$repo" merge-base --is-ancestor "$tested_base_sha" HEAD; then
  exit 1
fi
case "$plugin_scope_state" in
PLUGIN_CHANGE)
  set -o pipefail
  if ! base_plugin_version=$(git -C "$repo" show \
    "$tested_base_sha:plugins/team-skills/.codex-plugin/plugin.json" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["version"])'); then
    base_plugin_version=
    exit 1
  fi
  if ! test -n "$base_plugin_version"; then
    exit 1
  fi
  ;;
NO_PLUGIN_CHANGE)
  base_plugin_version=NOT_REQUIRED
  ;;
*)
  exit 1
  ;;
esac
```

Если переход `old_head_sha → new_head_sha` изменил любой `stable_path`, сначала
нужен `UNIQUE_HUNK_MAPPING_PASS`. Для каждого текстового WIP-hunk получите из
дельты `old_head_sha → recovery_stash_sha^2` preimage: строки контекста и
удаляемые строки, до восьми строк с каждой стороны; у границы файла требуется
весь доступный контекст. Эта точная последовательность bytes, разделённая
только Git-переносом `LF`, должна встречаться ровно один раз и в старом blob, и в
blob нового HEAD; соответствия всех hunks обязаны сохранять порядок и не
пересекаться. Для чистой вставки у начала или конца файла mapped-preimage
обязан по-прежнему касаться той же границы: так конкурентные prepend/prepend и
append/append не получают недоказанный порядок. Ноль или несколько совпадений,
изменённый контекст, special case
`No newline at end of file`, binary payload, mode-only drift, addition/deletion
того же path либо ошибка анализа дают `AMBIGUOUS_HUNK_MAPPING` и останавливают
процесс до `stash apply`. Recovery-stash при этом сохраняется.

Исполняемый verifier ниже получает все `stable_paths` через argv и выводит
только статус, не содержимое WIP. Любая ошибка команды, неизвестный тип entry
или неподдержанный случай закрывает гейт. Если сам этот reference входит в WIP,
не перечитывайте verifier из worktree после stash: используйте уже загруженный
блок ниже либо его точный blob из `${recovery_stash_sha}^2`, как в
`examples/good-04.md`:

```bash
if ((${#stable_paths[@]} == 0)); then
  unique_hunk_mapping=NOT_REQUIRED
elif ! unique_hunk_mapping=$(python3 - \
  "$repo" "$old_head_sha" "$new_head_sha" "$recovery_stash_sha" \
  "${stable_paths[@]}" <<'PY'
# UNIQUE_HUNK_VERIFIER_BEGIN
import os
import subprocess
import sys

if len(sys.argv) < 6:
    raise SystemExit(1)
repo, old_head, new_head, recovery, *paths = sys.argv[1:]
stash_index = f"{recovery}^2"


def git(*args: str) -> bytes:
    result = subprocess.run(
        ["git", "--literal-pathspecs", "-C", repo, *args],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError
    return result.stdout


def entry(revision: str, path: str):
    rows = [
        row
        for row in git("ls-tree", "-z", revision, "--", path).split(b"\0")
        if row
    ]
    if not rows:
        return None
    if len(rows) != 1:
        raise ValueError
    metadata, returned_path = rows[0].split(b"\t", 1)
    if returned_path != os.fsencode(path):
        raise ValueError
    mode, kind, oid = metadata.split()
    return mode, kind, oid


def lf_lines(payload: bytes) -> list[bytes]:
    parts = payload.split(b"\n")
    lines = [part + b"\n" for part in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def blob_lines(oid: bytes) -> list[bytes]:
    payload = git("cat-file", "blob", oid.decode("ascii"))
    if b"\0" in payload:
        raise ValueError
    return lf_lines(payload)


def unique_position(haystack: list[bytes], needle: list[bytes]):
    if not needle:
        raise ValueError
    matches = [
        index
        for index in range(len(haystack) - len(needle) + 1)
        if haystack[index : index + len(needle)] == needle
    ]
    if len(matches) != 1:
        raise ValueError
    return matches[0]


try:
    if not paths:
        raise ValueError
    same_path_drift = False
    for path in paths:
        old_entry = entry(old_head, path)
        new_entry = entry(new_head, path)
        wip_entry = entry(stash_index, path)
        for candidate in (old_entry, new_entry, wip_entry):
            if candidate is not None and candidate[1] != b"blob":
                raise ValueError
        if old_entry == wip_entry:
            raise ValueError
        if old_entry == new_entry:
            continue
        same_path_drift = True
        if None in (old_entry, new_entry, wip_entry):
            raise ValueError
        if not (
            old_entry[0] == new_entry[0] == wip_entry[0]
            and old_entry[1] == new_entry[1] == wip_entry[1] == b"blob"
        ):
            raise ValueError
        blob_lines(wip_entry[2])

        patch = git(
            "diff",
            "--binary",
            "--full-index",
            "--unified=8",
            "--no-renames",
            "--no-color",
            "--no-ext-diff",
            "--no-textconv",
            old_head,
            stash_index,
            "--",
            path,
        )
        if b"GIT binary patch" in patch or b"Binary files " in patch:
            raise ValueError

        hunks: list[tuple[list[bytes], list[bytes]]] = []
        current = None
        current_kinds = None
        for line in lf_lines(patch):
            if line.startswith(b"@@ "):
                if current is not None:
                    hunks.append((current, current_kinds))
                current = []
                current_kinds = []
            elif current is not None and line.startswith((b" ", b"-")):
                current.append(line[1:])
                current_kinds.append(line[:1])
            elif current is not None and line.startswith(b"+"):
                current_kinds.append(b"+")
                continue
            elif current is not None:
                raise ValueError
        if current is not None:
            hunks.append((current, current_kinds))
        if not hunks:
            raise ValueError

        old_lines = blob_lines(old_entry[2])
        new_lines = blob_lines(new_entry[2])
        old_end = new_end = -1
        for preimage, kinds in hunks:
            old_start = unique_position(old_lines, preimage)
            new_start = unique_position(new_lines, preimage)
            if old_start <= old_end or new_start <= new_end:
                raise ValueError
            old_end = old_start + len(preimage) - 1
            new_end = new_start + len(preimage) - 1
            if kinds[0] == b"+":
                if old_start != 0 or new_start != 0:
                    raise ValueError
            trailing_addition = len(kinds)
            while trailing_addition and kinds[trailing_addition - 1] == b"+":
                trailing_addition -= 1
            if (
                trailing_addition < len(kinds)
                and trailing_addition > 0
                and kinds[trailing_addition - 1] == b" "
            ):
                if old_end != len(old_lines) - 1 or new_end != len(new_lines) - 1:
                    raise ValueError

    print("UNIQUE_HUNK_MAPPING_PASS" if same_path_drift else "NOT_REQUIRED")
except Exception:
    raise SystemExit(1)
# UNIQUE_HUNK_VERIFIER_END
PY
); then
  unique_hunk_mapping=AMBIGUOUS_HUNK_MAPPING
fi
if ! test -n "$unique_hunk_mapping"; then
  exit 1
fi
```

Этот гейт нельзя заменять согласием двух Git merge/apply: оба могут одинаково
перенести правку на новую, а не исходную одинаковую строку. Если same-path drift
нет, отдельный unique-mapping gate не нужен. После PASS примените доказанный
stash без `pop` и без доверия старому index:

```bash
case "$unique_hunk_mapping" in
  NOT_REQUIRED|UNIQUE_HUNK_MAPPING_PASS) ;;
  *) exit 1 ;;
esac
if ! pre_apply_head_sha=$(git -C "$repo" rev-parse HEAD); then
  pre_apply_head_sha=
  exit 1
fi
if ! test "$pre_apply_head_sha" = "$new_head_sha"; then
  exit 1
fi
if ! git -C "$repo" stash apply "$recovery_stash_sha"; then
  exit 1
fi
if ! post_apply_head_sha=$(git -C "$repo" rev-parse HEAD); then
  post_apply_head_sha=
  exit 1
fi
if ! test "$post_apply_head_sha" = "$new_head_sha"; then
  exit 1
fi
if ! git -C "$repo" status --short --untracked-files=all; then
  exit 1
fi
if ! applied_unmerged=$(git -C "$repo" ls-files -u); then
  applied_unmerged=
  exit 1
fi
if ! test -z "$applied_unmerged"; then
  exit 1
fi
set -o pipefail
if ! applied_scope_state=$(
  {
    git -C "$repo" diff --name-only -z || exit 1
    git -C "$repo" diff --cached --name-only -z || exit 1
    git -C "$repo" ls-files --others --exclude-standard -z || exit 1
  } | python3 -c '
import os, sys
stable_count = int(sys.argv[1])
intended_count = int(sys.argv[2])
values = [os.fsencode(value) for value in sys.argv[3:]]
if len(values) != stable_count + intended_count:
    raise SystemExit(1)
stable = set(values[:stable_count])
intended = set(values[stable_count:])
rows = sys.stdin.buffer.read().split(b"\0")
if rows and rows[-1] == b"":
    rows.pop()
if any(not row for row in rows):
    raise SystemExit(1)
actual = set(rows)
if not stable.issubset(actual) or not actual.issubset(intended):
    raise SystemExit(1)
print("APPLIED_SCOPE_PASS")
' "${#stable_paths[@]}" "${#intended_paths[@]}" \
    "${stable_paths[@]}" "${intended_paths[@]}"
); then
  applied_scope_state=
  exit 1
fi
if ! test "$applied_scope_state" = APPLIED_SCOPE_PASS; then
  exit 1
fi
```

Используйте `apply`, а не `pop`: stash остаётся средством восстановления.
Индекс после движения базы не восстанавливайте автоматически — совпавшее
base-derived изменение, например уже поднятая версия manifest, может сделать
`apply --index` ложно конфликтным. Вместо этого сверяйте полный status и exact
scope, затем заново stage доказанные paths. До пересчёта derived-полей
`APPLIED_SCOPE_PASS` обязан подтвердить все `stable_paths` и отсутствие путей
вне intended scope;
base-derived manifest может временно отсутствовать, только если его старая
WIP-версия уже совпала с новой базой, а нормализованная содержательная часть
совпадает с сохранённым fingerprint. Любой лишний путь, пропавший stable path,
необъяснимый derived path, unmerged entry либо конфликт блокирует commit; stash
сохраняется.

После промежуточной сверки stage весь уже доказанный scope. `git add -A` без
pathspec здесь намеренно используется только когда все `stable_paths`
присутствуют, лишних путей нет, а отсутствие base-derived manifest объяснено
правилом выше. Полное равенство staged paths и `intended_paths` требуется
позже, после пересчёта и staging manifest. Такой порядок сохраняет удаления,
не превращая временно совпавшую с базой derived-версию в ложный missing path.

```bash
if ! git -C "$repo" add -A; then
  exit 1
fi
if ! unstaged_paths=$(git -C "$repo" diff --name-only); then
  unstaged_paths=
  exit 1
fi
if ! test -z "$unstaged_paths"; then
  exit 1
fi
if ! untracked_paths=$(git -C "$repo" ls-files --others --exclude-standard); then
  untracked_paths=
  exit 1
fi
if ! test -z "$untracked_paths"; then
  exit 1
fi
if ! new_head_sha=$(git -C "$repo" rev-parse HEAD); then
  new_head_sha=
  exit 1
fi
if ! test -n "$new_head_sha"; then
  exit 1
fi
if ! actual_tree=$(git -C "$repo" write-tree); then
  actual_tree=
  exit 1
fi
if ! test -n "$actual_tree"; then
  exit 1
fi

if ((${#stable_paths[@]} == 0)); then
  expected_tree=NOT_REQUIRED
else
if ! expected_index_dir=$(mktemp -d); then
  expected_index_dir=
  exit 1
fi
if ! test -n "$expected_index_dir"; then
  exit 1
fi
expected_index_path="${expected_index_dir:?}/index"
if ! test ! -e "$expected_index_path"; then
  exit 1
fi
if ! GIT_INDEX_FILE="$expected_index_path" \
  git -C "$repo" read-tree "$new_head_sha"; then
  exit 1
fi
set -o pipefail
if ! git --literal-pathspecs -C "$repo" diff \
    --binary --full-index --unified=8 --no-renames \
    --no-color --no-ext-diff --no-textconv \
    "$old_head_sha" "${recovery_stash_sha}^2" -- \
    "${stable_paths[@]}" \
  | GIT_INDEX_FILE="$expected_index_path" \
    git -C "$repo" -c apply.ignoreWhitespace=false apply \
      --cached -C8 --whitespace=nowarn --quiet -; then
  exit 1
fi
if ! expected_unmerged=$(GIT_INDEX_FILE="$expected_index_path" \
  git -C "$repo" ls-files -u); then
  exit 1
fi
if ! test -z "$expected_unmerged"; then
  exit 1
fi
if ! expected_tree=$(GIT_INDEX_FILE="$expected_index_path" \
  git -C "$repo" write-tree); then
  expected_tree=
  exit 1
fi
if ! test -n "$expected_tree"; then
  exit 1
fi
if ! confirmed_actual_tree=$(git -C "$repo" write-tree); then
  confirmed_actual_tree=
  exit 1
fi
if ! test "$confirmed_actual_tree" = "$actual_tree"; then
  exit 1
fi
if ! confirmed_new_head_sha=$(git -C "$repo" rev-parse HEAD); then
  confirmed_new_head_sha=
  exit 1
fi
if ! test "$confirmed_new_head_sha" = "$new_head_sha"; then
  exit 1
fi
if ! git --literal-pathspecs -C "$repo" diff \
  --quiet --no-ext-diff --no-textconv \
  "$expected_tree" "$actual_tree" -- "${stable_paths[@]}"; then
  exit 1
fi
if ! rm -f -- "$expected_index_path"; then
  exit 1
fi
if ! rmdir -- "$expected_index_dir"; then
  exit 1
fi
fi
# EMPTY_STABLE_PATHS_BRANCH_END
```

Эта проверка не сравнивает два base-dependent diff. Она загружает новый `HEAD`
в отдельный `GIT_INDEX_FILE`, применяет к нему точную binary/full-index дельту
`old_head_sha → recovery_stash_sha^2` напрямую, требуя весь доступный контекст
и минимум восемь строк с каждой стороны (`-C8`), и получает ожидаемое дерево на
новой базе. Full-index blob IDs нужны для binary payload, но сами по себе не
доказывают положение среди повторяющихся одинаковых строк; эту
неопределённость до apply закрывает `UNIQUE_HUNK_MAPPING_PASS`. После него
отдельный неконфликтующий hunk новой базы не создаёт ложный mismatch. Ошибка
применения, иной текст, пробелы, mode, addition, deletion или binary payload
дают ненулевой status либо отличие tree и блокируют commit. Настройка
`apply.ignoreWhitespace=false` запрещает локальной Git-конфигурации ослабить
сравнение. Если `stable_paths` пуст, зафиксируйте это отдельным маркером и не
запускайте команды с пустым pathspec. Ошибка любого звена pipeline, unmerged
entry, пустой object ID или ненулевой `git diff --quiet` останавливают процесс.

До вычисления итогового `tested_tree` в ветке `PLUGIN_CHANGE` пересчитайте
`version` manifest относительно нового `origin/main` с сохранённым
`version_bump_kind`, stage его и сравните канонический JSON без `version` с
сохранённым fingerprint. Отдельно докажите, что новая `version` равна
ожидаемому следующему `patch`, `minor` или `major` semver того же сохранённого
типа. При `NO_PLUGIN_CHANGE` manifest не добавляется, а эти derived-проверки
явно пропускаются как `NOT_REQUIRED`. Равенство exact expected tree на
`stable_paths`, нормализованного manifest и правила версии в plugin-ветке —
обязательный гейт автоматического продолжения. Если любой обязательный compare
отличается, даже при чистом apply, commit запрещён: stash сохраняется, а точный
path/hunk scope требует явной сверки. Не заменяйте это сравнением только имён
файлов.

После пересчёта derived-версии закройте все три compare исполняемым гейтом:

```bash
# PLUGIN_SEMVER_GATE_BEGIN
case "$plugin_scope_state" in
PLUGIN_CHANGE)
  manifest_path="$repo/$manifest_relative_path"
  if ! git -C "$repo" add -- "$manifest_relative_path"; then
    exit 1
  fi
  if ! recovered_manifest_payload_fingerprint=$(python3 -c '
import hashlib, json, pathlib, sys
p = pathlib.Path(sys.argv[1])
d = json.loads(p.read_text(encoding="utf-8"))
d.pop("version", None)
payload = json.dumps(d, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
print(hashlib.sha256(payload.encode("utf-8")).hexdigest())
' "$manifest_path"); then
    recovered_manifest_payload_fingerprint=
    exit 1
  fi
  if ! test "$recovered_manifest_payload_fingerprint" = \
    "$manifest_payload_fingerprint"; then
    exit 1
  fi
  if ! semver_recalc_state=$(python3 -c '
import json, pathlib, re, sys
base_version, bump_kind, manifest_path = sys.argv[1:]
if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", base_version):
    raise SystemExit(1)
major, minor, patch = map(int, base_version.split("."))
if bump_kind == "patch":
    expected = f"{major}.{minor}.{patch + 1}"
elif bump_kind == "minor":
    expected = f"{major}.{minor + 1}.0"
elif bump_kind == "major":
    expected = f"{major + 1}.0.0"
else:
    raise SystemExit(1)
actual = json.loads(pathlib.Path(manifest_path).read_text(encoding="utf-8")).get("version")
if actual != expected:
    raise SystemExit(1)
print("SEMVER_RECALC_PASS")
' "$base_plugin_version" "$version_bump_kind" "$manifest_path"); then
    semver_recalc_state=
    exit 1
  fi
  if ! test "$semver_recalc_state" = SEMVER_RECALC_PASS; then
    exit 1
  fi
  ;;
NO_PLUGIN_CHANGE)
  recovered_manifest_payload_fingerprint=NOT_REQUIRED
  semver_recalc_state=NOT_REQUIRED
  ;;
*)
  exit 1
  ;;
esac
# PLUGIN_SEMVER_GATE_END
set -o pipefail
if ! staged_scope_state=$(
  git -C "$repo" diff --cached --name-only -z |
    python3 -c '
import os, sys
intended_count = int(sys.argv[1])
intended = {os.fsencode(value) for value in sys.argv[2:]}
if len(sys.argv[2:]) != intended_count or len(intended) != intended_count:
    raise SystemExit(1)
rows = sys.stdin.buffer.read().split(b"\0")
if rows and rows[-1] == b"":
    rows.pop()
if any(not row for row in rows) or set(rows) != intended:
    raise SystemExit(1)
print("STAGED_SCOPE_PASS")
' "${#intended_paths[@]}" "${intended_paths[@]}"
); then
  staged_scope_state=
  exit 1
fi
if ! test "$staged_scope_state" = STAGED_SCOPE_PASS; then
  exit 1
fi
if ! tested_tree=$(git -C "$repo" write-tree); then
  tested_tree=
  exit 1
fi
if ! test -n "$tested_tree"; then
  exit 1
fi
```

После условной derived-нормализации сохраните точный staged path set и
убедитесь, что он в точности равен полному `intended_paths`: manifest входит в
него только при `PLUGIN_CHANGE`. Только после обязательных для выбранной ветки
compare зафиксируйте
`tested_tree=$(git -C "$repo" write-tree)`.
Повторите `git diff --check`, `git diff --cached --check`,
полную suite, base-sensitive checks и затронутые живые пробы. После каждого
такого test run заново пройдите remote gate и получите `verified_base_sha` до
commit, затем выполните непосредственный commit gate. После commit установите
`verified_head_sha` и выполните общие проверки tree и чистоты из начала
reference.

### 3. Удалить Только Созданный Процессом Stash

До доказательства, что `verified_head_sha` содержит ровно `tested_tree`, stash
не удаляйте. После доказанного commit заново получите список `%H`, `%gd`, `%gs`
и найдите ровно одну текущую запись, у которой SHA равен
`recovery_stash_sha`, subject равен `expected_stash_subject`, а SHA отсутствовал
в снимке до workflow. Не используйте старую позицию или предположение
`stash@{0}`.

Cleanup разрешён только при исключительном контроле процесса над stash reflog
на время финального compare-and-drop. Непосредственно перед удалением ещё раз
разрешите найденный selector и сравните object SHA. Если исключительный
контроль не доказан, пропустите только drop: сохраните recovery-stash, назовите
его SHA и команду восстановления, затем продолжите к pre-push gate:

```bash
# RECOVERY_STASH_CLEANUP_BEGIN
if test "${stash_reflog_exclusive_state:-UNPROVEN}" = \
  EXCLUSIVE_CONTROL_PASS; then
set -o pipefail
if ! recovery_stash_ref=$(
  git -C "$repo" stash list --format='%H%x09%gd%x09%gs' |
    awk -F '\t' -v sha="$recovery_stash_sha" \
      -v subject="$expected_stash_subject" \
      '$1 == sha && $3 == subject { print $2 }'
); then
  recovery_stash_ref=
  exit 1
fi
if ! recovery_stash_ref_count=$(
  printf '%s\n' "$recovery_stash_ref" | sed '/^$/d' | wc -l | tr -d ' '
); then
  recovery_stash_ref_count=
  exit 1
fi
if ! test "$recovery_stash_ref_count" = 1; then
  exit 1
fi
if ! drop_candidate_sha=$(
  git -C "$repo" rev-parse "$recovery_stash_ref"
); then
  drop_candidate_sha=
  exit 1
fi
if ! test "$drop_candidate_sha" = "$recovery_stash_sha"; then
  exit 1
fi
if ! git -C "$repo" stash drop "$recovery_stash_ref"; then
  exit 1
fi
set -o pipefail
if ! git -C "$repo" stash list --format='%H' | LC_ALL=C sort \
  >"$stash_after_path"; then
  exit 1
fi
if ! cmp -s "$stash_before_path" "$stash_after_path"; then
  exit 1
fi
if ! rm -f -- "$stash_before_path" "$stash_after_path" "$stash_new_path"; then
  exit 1
fi
if ! rmdir -- "$stash_evidence_dir"; then
  exit 1
fi
recovery_stash_cleanup_state=DROPPED
recovery_stash_restore_command=NOT_REQUIRED
else
recovery_stash_cleanup_state=PRESERVED
printf -v recovery_stash_restore_command \
  'git -C %q stash apply %q' "$repo" "$recovery_stash_sha"
printf 'Резервный stash сохранён: %s\nКоманда восстановления: %s\n' \
  "$recovery_stash_sha" "$recovery_stash_restore_command"
fi
case "$recovery_stash_cleanup_state" in
  DROPPED|PRESERVED) ;;
  *) exit 1 ;;
esac
# RECOVERY_STASH_CLEANUP_END
```

После drop проверьте, что созданный SHA исчез из stash list, а полный набор
исходных SHA остался прежним. Если запись не уникальна, selector
перенумеровался, stash reflog мог меняться другим процессом или post-check не
доказуем до mutation, ничего не удаляйте: сохраните object SHA, укажите
восстановление `git -C "$repo" stash apply <recovery_stash_sha>`. Ветка
`UNPROVEN` выше продолжает delivery без попытки cleanup; неожиданный сбой уже
начатой cleanup-процедуры останавливает процесс до сверки фактического stash
list. Исходные stashes не изменяйте.

## Короткий Гейт Перед Push

После последнего fetch push разрешён, только если одновременно:

- `pre_push_base_sha == verified_base_sha`;
- `verified_base_sha` является предком текущего `HEAD`;
- текущий `HEAD == verified_head_sha`;
- текущий `HEAD^{tree} == tested_tree`;
- staged, unstaged и untracked отсутствуют.

Если изменились база, HEAD или tree, результаты тестов устарели: вернитесь к
нужному потоку, повторите проверки и получите новые доказательства.

Сам гейт выполняйте fail-closed, включая producer-команды:

```bash
if ! git -C "$repo" fetch origin --prune; then
  exit 1
fi
if ! pre_push_base_sha=$(git -C "$repo" rev-parse origin/main); then
  pre_push_base_sha=
  exit 1
fi
if ! test "$pre_push_base_sha" = "$verified_base_sha"; then
  exit 1
fi
if ! git -C "$repo" merge-base --is-ancestor "$verified_base_sha" HEAD; then
  exit 1
fi
if ! pre_push_head_sha=$(git -C "$repo" rev-parse HEAD); then
  pre_push_head_sha=
  exit 1
fi
if ! test "$pre_push_head_sha" = "$verified_head_sha"; then
  exit 1
fi
if ! pre_push_tree_sha=$(git -C "$repo" rev-parse 'HEAD^{tree}'); then
  pre_push_tree_sha=
  exit 1
fi
if ! test "$pre_push_tree_sha" = "$tested_tree"; then
  exit 1
fi
if ! pre_push_status=$(
  git -C "$repo" status --porcelain=v1 --untracked-files=all
); then
  pre_push_status=
  exit 1
fi
if ! test -z "$pre_push_status"; then
  exit 1
fi
```

Обычная новая ветка публикуется обычным push. Если уже опубликованная ветка
была переписана rebase/amend, используйте только remote SHA, захваченный до
переписывания, и явный lease:

```bash
if ! git -C "$repo" push origin "HEAD:refs/heads/$branch" \
  "--force-with-lease=refs/heads/$branch:$expected_remote_sha"; then
  exit 1
fi
```

Эквивалентный контракт команды:
`--force-with-lease=refs/heads/<branch>:<expected_remote_sha>`. Общий
`--force-with-lease` без ожидаемого SHA недостаточен: он не фиксирует
доказанное remote-состояние, относительно которого началось переписывание.

## Readback После Push, До PR

Успешный ответ `git push` ещё не является границей открытия PR. Сразу после
push заново fetch'ните base и отдельно прочитайте точный remote head:

```bash
if ! git -C "$repo" fetch origin --prune; then
  exit 1
fi
if ! post_push_base_sha=$(git -C "$repo" rev-parse origin/main); then
  post_push_base_sha=
  exit 1
fi
set -o pipefail
if ! post_push_head_sha=$(
  git -C "$repo" ls-remote --heads origin "refs/heads/$branch" |
    awk 'NF == 2 { print $1 }'
); then
  post_push_head_sha=
  exit 1
fi
if ! post_push_head_count=$(
  printf '%s\n' "$post_push_head_sha" |
    sed '/^$/d' | wc -l | tr -d ' '
); then
  post_push_head_count=
  exit 1
fi
if ! test "$post_push_head_count" = 1; then
  exit 1
fi
if ! test "$post_push_head_sha" = "$verified_head_sha"; then
  exit 1
fi
if ! test "$post_push_base_sha" = "$verified_base_sha"; then
  exit 1
fi
```

Сначала проверяется head: его отсутствие, несколько строк или несовпадение с
`verified_head_sha` останавливает процесс и запрещает PR. Если head совпал, но
`origin/main` продвинулся, не открывайте и не обновляйте PR: вернитесь к
нужному потоку, перенесите ветку, пересчитайте semver при необходимости и
повторите тесты, pre-push gate, push с exact lease и этот readback. Только
совпавшие remote head и base разрешают переход к PR.
