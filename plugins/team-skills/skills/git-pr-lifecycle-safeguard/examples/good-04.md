# Хороший Пример

## Вход

«Пока шли тесты, `main` продвинулся. Перед commit ещё раз сверь базу и не
потеряй WIP. Мой scope — `src/change.py`, `tests/test_change.py` и Codex plugin
manifest; в дереве может лежать чужой файл. Ветка уже опубликована.»

## Ожидаемое Поведение

Codex сначала получает полный status, включая untracked:

```bash
repo=/path/to/repo
if ! branch=$(git -C "$repo" branch --show-current); then
  branch=
  exit 1
fi
if ! test -n "$branch"; then
  exit 1
fi
intended_paths=(
  src/change.py
  tests/test_change.py
  plugins/team-skills/.codex-plugin/plugin.json
)
stable_paths=(src/change.py tests/test_change.py)
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
if ! git -C "$repo" status --short --untracked-files=all; then
  exit 1
fi
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
```

Если status содержит хотя бы один путь вне `intended_paths`, это mixed WIP.
Codex останавливается до `stash` и `rebase` и запрашивает один выбор состава
патча. Следующие команды разрешены только после того, как полный dirty path set
доказанно и в точности совпал с intended scope. То же правило действует, если
в одном intended-файле смешаны нужные и чужие hunks: равенство имени файла не
разрешает общий staging, пока hunk scope нельзя безопасно разделить. Только
read-only сверка всех hunks может установить
`hunk_scope_state=INTENDED_HUNKS_ONLY`; при неопределённости маркер не
устанавливается и следующий блок останавливается до `add -A`.

Для уже опубликованной ветки Codex до переписывания сохраняет remote SHA,
затем фиксирует проверенную базу и точный staged tree:

```bash
if ! test "$initial_path_scope_state" = INTENDED_PATH_SCOPE_PASS; then
  exit 1
fi
if ! test "${hunk_scope_state:-UNPROVEN}" = INTENDED_HUNKS_ONLY; then
  exit 1
fi
if ! git -C "$repo" fetch origin --prune; then
  exit 1
fi
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
if ! tested_base_sha=$(git -C "$repo" rev-parse origin/main); then
  tested_base_sha=
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
if ! tested_tree=$(git -C "$repo" write-tree); then
  tested_tree=
  exit 1
fi
if ! test -n "$tested_tree"; then
  exit 1
fi
if ! git -C "$repo" diff --cached --check; then
  exit 1
fi
if ! (cd -- "$repo" && python -m pytest); then
  exit 1
fi
```

После тестов новый `origin/main` отличается, поэтому commit запрещён. Codex
сначала сохраняет точный `intended_index_tree`. После создания recovery-stash
он доказывает, что parent записи равен старому HEAD, а index и worktree trees
равны именно сохранённому дереву. Для manifest отдельно хешируется канонический
JSON без base-derived поля `version`: содержательная часть должна сохраниться,
а сама версия после переноса обязана быть пересчитана. До stash отдельно
доказано, что переход `0.7.12 → 0.7.13` был выбранным `patch` bump; Codex
сохраняет этот тип, а не выводит его заново после drift. Затем Codex доказывает
создание ровно одного нового recovery-stash сравнением object SHA, а не чтением
`stash@{0}`:

```bash
if ! git -C "$repo" fetch origin --prune; then
  exit 1
fi
if ! current_base_sha=$(git -C "$repo" rev-parse origin/main); then
  current_base_sha=
  exit 1
fi
if ! test "$current_base_sha" != "$tested_base_sha"; then
  exit 1
fi

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
if ! old_head_sha=$(git -C "$repo" rev-parse HEAD); then
  old_head_sha=
  exit 1
fi
if ! test -n "$old_head_sha"; then
  exit 1
fi
version_bump_kind=patch
if ! git -C "$repo" add -A; then
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
if ! manifest_payload_fingerprint=$(python3 -c '
import hashlib, json, pathlib, sys
p = pathlib.Path(sys.argv[1])
d = json.loads(p.read_text(encoding="utf-8"))
d.pop("version", None)
payload = json.dumps(d, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
print(hashlib.sha256(payload.encode("utf-8")).hexdigest())
' "$repo/plugins/team-skills/.codex-plugin/plugin.json"); then
  manifest_payload_fingerprint=
  exit 1
fi
if ! test -n "$manifest_payload_fingerprint"; then
  exit 1
fi
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

expected_stash_subject="On ${branch}: ${recovery_message}"
if ! actual_stash_subject=$(
  git -C "$repo" show -s --format='%s' "$recovery_stash_sha"
); then
  actual_stash_subject=
  exit 1
fi
if ! test "$actual_stash_subject" = "$expected_stash_subject"; then exit 1; fi
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
if ! test "$stash_base_sha" = "$old_head_sha"; then exit 1; fi
if ! test "$stash_index_base_sha" = "$old_head_sha"; then exit 1; fi
if ! test "$stash_index_tree" = "$intended_index_tree"; then exit 1; fi
if ! test "$stash_worktree_tree" = "$intended_index_tree"; then exit 1; fi
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

Только при глобально чистом дереве Codex переносит ветку. До `stash apply` он
сравнивает same-path drift с исходными текстовыми hunks. В этом примере новый
`main` изменил отдельный hunk: каждый preimage из контекста и удаляемых строк
встречается ровно один раз в старом и новом blob, порядок не изменён, поэтому
получен `UNIQUE_HUNK_MAPPING_PASS`. Если бы `main` вставил ещё одну одинаковую
строку рядом с intended-hunk, результат был бы `AMBIGUOUS_HUNK_MAPPING`, stash
остался бы сохранён, а apply и commit не выполнялись бы.

Поскольку новый `origin/main` мог уже повысить версию plugin, Codex читает его
актуальный semver и через `apply_patch` пересчитывает manifest относительно
именно новой базы до staging и повторных тестов. Сам verifier извлекается по
blob SHA из доказанного index tree recovery-stash, а не из временно старого
worktree после stash:

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
verifier_reference_path="plugins/team-skills/skills/\
git-pr-lifecycle-safeguard/references/late-base-gate.md"
if ! verifier_blob_sha=$(git -C "$repo" rev-parse \
  "${recovery_stash_sha}^2:${verifier_reference_path}"); then
  verifier_blob_sha=
  exit 1
fi
if ! test -n "$verifier_blob_sha"; then
  exit 1
fi
if ! verifier_document=$(git -C "$repo" cat-file blob "$verifier_blob_sha"); then
  verifier_document=
  exit 1
fi
set -o pipefail
if ! verifier_marker_counts=$(printf '%s\n' "$verifier_document" | awk '
  $0 == "# UNIQUE_HUNK_VERIFIER_BEGIN" { begin += 1 }
  $0 == "# UNIQUE_HUNK_VERIFIER_END" { end += 1 }
  END { print begin ":" end }
'); then
  verifier_marker_counts=
  exit 1
fi
if ! test "$verifier_marker_counts" = 1:1; then
  exit 1
fi
if ! verifier_source=$(printf '%s\n' "$verifier_document" | sed -n \
  '/^# UNIQUE_HUNK_VERIFIER_BEGIN$/,/^# UNIQUE_HUNK_VERIFIER_END$/p' \
); then
  verifier_source=
  exit 1
fi
if ! test -n "$verifier_source"; then
  exit 1
fi
if ! unique_hunk_mapping=$(printf '%s\n' "$verifier_source" | python3 - \
  "$repo" "$old_head_sha" "$new_head_sha" "$recovery_stash_sha" \
  "${stable_paths[@]}"); then
  unique_hunk_mapping=AMBIGUOUS_HUNK_MAPPING
fi
if ! test "$unique_hunk_mapping" = UNIQUE_HUNK_MAPPING_PASS; then
  exit 1
fi
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
if ! tested_base_sha=$(git -C "$repo" rev-parse origin/main); then
  tested_base_sha=
  exit 1
fi
if ! base_plugin_version=$(git -C "$repo" show \
  "$tested_base_sha:plugins/team-skills/.codex-plugin/plugin.json" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["version"])'); then
  base_plugin_version=
  exit 1
fi
if ! test -n "$base_plugin_version"; then
  exit 1
fi
```

После apply все `stable_paths` обязаны присутствовать в status и лишних путей
быть не должно. Manifest может временно отсутствовать: старая WIP-версия
`0.7.13` уже совпала с новой базой. Это допустимо только после проверки его
нормализованной содержательной части; полный intended path set проверяется
после установки новой derived-версии.

Codex устанавливает в manifest следующий Codex plugin semver того же
`version_bump_kind` относительно `base_plugin_version`. Если исходный выбор был
`minor` или `major`, он сохраняет именно этот тип; неизвестный тип останавливает
автоматическое продолжение. Затем Codex в изолированном `GIT_INDEX_FILE`
загружает новый HEAD и напрямую применяет точную full-index дельту старого HEAD
к доказанному index parent stash с восемью строками контекста. Так отдельный
неконфликтующий hunk нового `main` в том же файле сохраняется, а одинаковый
текст, изменённый в другом месте, уже не может пройти unique-hunk gate. Codex
сравнивает полученный
`expected_tree` с фактическим staged tree на всех `stable_paths`, отдельно
проверяет содержательную часть manifest и ожидаемую новую версию и лишь после
этого связывает повторные тесты с tree:

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
if ! recovered_manifest_payload_fingerprint=$(python3 -c '
import hashlib, json, pathlib, sys
p = pathlib.Path(sys.argv[1])
d = json.loads(p.read_text(encoding="utf-8"))
d.pop("version", None)
payload = json.dumps(d, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
print(hashlib.sha256(payload.encode("utf-8")).hexdigest())
' "$repo/plugins/team-skills/.codex-plugin/plugin.json"); then
  recovered_manifest_payload_fingerprint=
  exit 1
fi
if ! test -n "$recovered_manifest_payload_fingerprint"; then
  exit 1
fi
if ! test "$recovered_manifest_payload_fingerprint" = \
  "$manifest_payload_fingerprint"; then
  exit 1
fi
manifest_path="$repo/plugins/team-skills/.codex-plugin/plugin.json"
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
if ! git -C "$repo" diff --cached --check; then
  exit 1
fi
if ! (cd -- "$repo" && python -m pytest); then
  exit 1
fi
```

После повторного test run Codex снова получает remote refs. Только успешные
compare и ancestry устанавливают `verified_base_sha`, причём до commit:

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
if ! git -C "$repo" commit -m "Сохранить проверенное изменение"; then
  exit 1
fi
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

После доказанного commit Codex при исключительном контроле stash reflog заново
находит созданную запись по object SHA и точному subject, а не по старой
позиции. Непосредственно перед drop он повторно сверяет SHA, удаляет только эту
запись и проверяет, что исходные stashes сохранились. Если исключительный
контроль не доказан, Codex сохраняет recovery-stash, сообщает SHA и команду
восстановления и продолжает к pre-push gate без `stash drop`:

```bash
# RECOVERY_STASH_CLEANUP_BEGIN
if test "${stash_reflog_exclusive_state:-UNPROVEN}" = \
  EXCLUSIVE_CONTROL_PASS; then
set -o pipefail
if ! stash_ref=$(git -C "$repo" stash list --format='%H%x09%gd%x09%gs' |
  awk -F '\t' -v sha="$recovery_stash_sha" -v subject="$expected_stash_subject" \
    '$1 == sha && $3 == subject { print $2 }'); then
  stash_ref=
  exit 1
fi
if ! stash_ref_count=$(
  printf '%s\n' "$stash_ref" | sed '/^$/d' | wc -l | tr -d ' '
); then
  stash_ref_count=
  exit 1
fi
if ! test "$stash_ref_count" = 1; then
  exit 1
fi
if ! drop_candidate_sha=$(git -C "$repo" rev-parse "$stash_ref"); then
  drop_candidate_sha=
  exit 1
fi
if ! test "$drop_candidate_sha" = "$recovery_stash_sha"; then
  exit 1
fi
if ! git -C "$repo" stash drop "$stash_ref"; then
  exit 1
fi
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

Перед push он доказывает неизменность базы, HEAD и tree:

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
if ! git -C "$repo" push origin "HEAD:refs/heads/$branch" \
  "--force-with-lease=refs/heads/$branch:$expected_remote_sha"; then
  exit 1
fi
```

После push, но до PR, Codex заново читает живую base и точный remote head.
Несовпадение head останавливает процесс; drift base возвращает к rebase,
повторным тестам и новому push:

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

## Нельзя

Нельзя продолжать при mixed WIP, включая неразделимые чужие hunks внутри
intended-файла, при no-op stash, при непустом дереве после stash, при
`AMBIGUOUS_HUNK_MAPPING`, пустом или недоказанном temp-пути, несовпадении
expected/actual tree, нормализованного manifest, версии или subject.
Нельзя применять stash через `pop`, слепо повторять конфликтующий
`apply --index`, удалять recovery-запись без повторной идентификации по SHA и
исключительного контроля stash reflog, считать старые тесты актуальными после
rebase, использовать `stash@{0}` как доказательство владения, выполнять общий
`--force-with-lease` без ожидаемого remote SHA или открывать PR до post-push
readback base и head.
