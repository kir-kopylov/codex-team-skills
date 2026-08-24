from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from conftest import ROOT


SKILL_DIR = (
    ROOT
    / "plugins"
    / "team-skills"
    / "skills"
    / "git-pr-lifecycle-safeguard"
)
SKILL = SKILL_DIR / "SKILL.md"
RECOVERY = SKILL_DIR / "references" / "late-base-gate.md"


def _git(
    repo: Path, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed:\nstdout={result.stdout}\nstderr={result.stderr}"
        )
    return result


def _init_repo(repo: Path) -> Path:
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "branch", "-m", "main")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "tracked.txt").write_text("initial\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-qm", "initial")
    return repo


def _stash_rows(repo: Path) -> list[str]:
    output = _git(repo, "stash", "list", "--format=%H%x09%gd%x09%gs").stdout
    return output.splitlines()


def _precommit_gate_is_clean(repo: Path, tested_tree: str) -> bool:
    index_tree = _git(repo, "write-tree", check=False)
    return (
        index_tree.returncode == 0
        and index_tree.stdout.strip() == tested_tree
        and _git(repo, "diff", "--quiet", check=False).returncode == 0
        and not _git(repo, "ls-files", "--others", "--exclude-standard").stdout
        and not _git(repo, "ls-files", "-u").stdout
    )


def _hash_git_object(repo: Path, payload: bytes) -> str:
    digest = subprocess.run(
        ["git", "-C", str(repo), "hash-object", "--stdin"],
        input=payload,
        check=False,
        capture_output=True,
    )
    assert digest.returncode == 0, digest.stderr.decode(errors="replace")
    return digest.stdout.decode("ascii").strip()


def _raw_wip_fingerprint(repo: Path, base: str, paths: list[str]) -> str:
    diff = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "diff",
            "--cached",
            "--binary",
            "--full-index",
            "--no-renames",
            "--no-color",
            "--no-ext-diff",
            "--no-textconv",
            base,
            "--",
            *paths,
        ],
        check=False,
        capture_output=True,
    )
    assert diff.returncode == 0, diff.stderr.decode(errors="replace")
    return _hash_git_object(repo, diff.stdout)


def _assert_stash_captured_index(
    repo: Path,
    recovery_sha: str,
    old_head_sha: str,
    intended_index_tree: str,
) -> None:
    assert _git(repo, "rev-parse", f"{recovery_sha}^1").stdout.strip() == old_head_sha
    assert (
        _git(repo, "rev-parse", f"{recovery_sha}^2^{{tree}}").stdout.strip()
        == intended_index_tree
    )
    assert (
        _git(repo, "rev-parse", f"{recovery_sha}^2^1").stdout.strip()
        == old_head_sha
    )
    assert (
        _git(repo, "rev-parse", f"{recovery_sha}^{{tree}}").stdout.strip()
        == intended_index_tree
    )


def _expected_tree_from_stash(
    repo: Path,
    old_head_sha: str,
    recovery_sha: str,
    new_head: str,
    paths: list[str],
    index_path: Path,
) -> str:
    assert paths
    index_path.unlink(missing_ok=True)
    env = os.environ.copy()
    env["GIT_INDEX_FILE"] = str(index_path)

    read_tree = subprocess.run(
        ["git", "-C", str(repo), "read-tree", new_head],
        env=env,
        check=False,
        capture_output=True,
    )
    assert read_tree.returncode == 0, read_tree.stderr.decode(errors="replace")

    delta = subprocess.run(
        [
            "git",
            "--literal-pathspecs",
            "-C",
            str(repo),
            "diff",
            "--binary",
            "--full-index",
            "--unified=8",
            "--no-renames",
            "--no-color",
            "--no-ext-diff",
            "--no-textconv",
            old_head_sha,
            f"{recovery_sha}^2",
            "--",
            *paths,
        ],
        check=False,
        capture_output=True,
    )
    assert delta.returncode == 0, delta.stderr.decode(errors="replace")

    apply_delta = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "apply.ignoreWhitespace=false",
            "apply",
            "--cached",
            "-C8",
            "--whitespace=nowarn",
            "--quiet",
            "-",
        ],
        input=delta.stdout,
        env=env,
        check=False,
        capture_output=True,
    )
    assert apply_delta.returncode == 0, apply_delta.stderr.decode(errors="replace")

    unmerged = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-u"],
        env=env,
        check=False,
        capture_output=True,
    )
    assert unmerged.returncode == 0, unmerged.stderr.decode(errors="replace")
    assert unmerged.stdout == b""

    expected_tree = subprocess.run(
        ["git", "-C", str(repo), "write-tree"],
        env=env,
        check=False,
        capture_output=True,
    )
    assert expected_tree.returncode == 0, expected_tree.stderr.decode(
        errors="replace"
    )
    expected_tree_sha = expected_tree.stdout.decode("ascii").strip()
    assert expected_tree_sha
    return expected_tree_sha


def _trees_match_paths(
    repo: Path,
    expected_tree: str,
    actual_tree: str,
    paths: list[str],
) -> bool:
    assert paths
    result = subprocess.run(
        [
            "git",
            "--literal-pathspecs",
            "-C",
            str(repo),
            "diff",
            "--quiet",
            "--no-ext-diff",
            "--no-textconv",
            expected_tree,
            actual_tree,
            "--",
            *paths,
        ],
        check=False,
        capture_output=True,
    )
    assert result.returncode in {0, 1}, result.stderr.decode(errors="replace")
    return result.returncode == 0


def _extract_unique_hunk_verifier_source(document: str) -> str:
    begin = "# UNIQUE_HUNK_VERIFIER_BEGIN"
    end = "# UNIQUE_HUNK_VERIFIER_END"
    assert document.count(begin) == 1
    assert document.count(end) == 1
    source = document.split(begin, 1)[1].split(end, 1)[0]
    assert source.strip()
    return source


def _unique_hunk_verifier_source() -> str:
    return _extract_unique_hunk_verifier_source(
        RECOVERY.read_text(encoding="utf-8")
    )


def _stable_scope_gate_source() -> str:
    document = RECOVERY.read_text(encoding="utf-8")
    begin = "# STABLE_SCOPE_GATE_BEGIN"
    end = "# STABLE_SCOPE_GATE_END"
    assert document.count(begin) == 1
    assert document.count(end) == 1
    source = document.split(begin, 1)[1].split(end, 1)[0]
    assert source.strip()
    return source


def _recovery_stash_cleanup_source(path: Path = RECOVERY) -> str:
    document = path.read_text(encoding="utf-8")
    begin = "# RECOVERY_STASH_CLEANUP_BEGIN"
    end = "# RECOVERY_STASH_CLEANUP_END"
    assert document.count(begin) == 1
    assert document.count(end) == 1
    source = document.split(begin, 1)[1].split(end, 1)[0]
    assert source.strip()
    return source


def _run_stable_scope_gate(
    plugin_state: str,
    stable_paths: list[str],
    intended_paths: list[str],
) -> subprocess.CompletedProcess[str]:
    driver = f"""
plugin_scope_state=$1
manifest_relative_path=$2
requested_stable_count=$3
shift 3
stable_paths=()
while (( requested_stable_count > 0 )); do
  stable_paths+=("$1")
  shift
  requested_stable_count=$((requested_stable_count - 1))
done
intended_paths=("$@")
{_stable_scope_gate_source()}
printf 'DOWNSTREAM_REACHED\n'
"""
    return subprocess.run(
        [
            "bash",
            "-c",
            driver,
            "stable-scope-probe",
            plugin_state,
            "plugins/team-skills/.codex-plugin/plugin.json",
            str(len(stable_paths)),
            *stable_paths,
            *intended_paths,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def _unique_hunk_verifier_source_from_revision(
    repo: Path,
    revision: str,
    path: str,
) -> tuple[str, str]:
    blob_sha = _git(repo, "rev-parse", f"{revision}:{path}").stdout.strip()
    assert blob_sha
    document = _git(repo, "cat-file", "blob", blob_sha).stdout
    return blob_sha, _extract_unique_hunk_verifier_source(document)


def _unique_hunk_mapping_status(
    repo: Path,
    old_head_sha: str,
    new_head_sha: str,
    recovery_sha: str,
    paths: list[str],
    source: str | None = None,
) -> str:
    assert paths
    result = subprocess.run(
        [
            sys.executable,
            "-",
            str(repo),
            old_head_sha,
            new_head_sha,
            recovery_sha,
            *paths,
        ],
        input=source if source is not None else _unique_hunk_verifier_source(),
        text=True,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        return "AMBIGUOUS_HUNK_MAPPING"
    status = result.stdout.strip()
    assert status in {"NOT_REQUIRED", "UNIQUE_HUNK_MAPPING_PASS"}
    assert result.stderr == ""
    return status


def _manifest_payload_fingerprint(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("version", None)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _semver_bump_kind(base: str, intended: str) -> str:
    base_parts = tuple(int(part) for part in base.split("."))
    intended_parts = tuple(int(part) for part in intended.split("."))
    assert len(base_parts) == len(intended_parts) == 3
    assert intended_parts > base_parts
    if intended_parts[0] != base_parts[0]:
        return "major"
    if intended_parts[1] != base_parts[1]:
        return "minor"
    return "patch"


def _next_semver(base: str, bump_kind: str) -> str:
    major, minor, patch = (int(part) for part in base.split("."))
    if bump_kind == "major":
        return f"{major + 1}.0.0"
    if bump_kind == "minor":
        return f"{major}.{minor + 1}.0"
    assert bump_kind == "patch"
    return f"{major}.{minor}.{patch + 1}"


def test_pr_metadata_edit_requires_fresh_pull_request_event() -> None:
    body = SKILL.read_text(encoding="utf-8")
    pr_mode = body.split("## Режим 1: local-wip-to-clean-pr", 1)[1].split(
        "## Режим 2: post-merge-branch-housekeeping", 1
    )[0]
    normalized = " ".join(pr_mode.split())

    for invariant in (
        "старый зелёный job не подтверждает новые метаданные",
        "новый `pull_request` event с уже исправленными метаданными",
        "простой rerun старого job может использовать прежний event payload",
        "Не создавайте бессодержательный commit только ради нового события",
    ):
        assert invariant in normalized


def test_explicit_approval_is_bound_to_the_exact_publish_candidate() -> None:
    text = SKILL.read_text(encoding="utf-8")
    section = text.split("## Явная Граница Одобрения Перед Публикацией", 1)[1]
    section = section.split("\n## ", 1)[0]
    section = " ".join(section.split())

    for invariant in (
        "не добавляет отдельный вопрос об одобрении",
        "пользователь явно потребовал",
        "выбранный до одобрения режим границы",
        "По умолчанию `strict-base`",
        "Режим `target-only` допустим",
        "до одобрения явно согласился",
        "Менять режим после одобрения нельзя",
        "git remote get-url --all \"<remote>\"",
        "git remote get-url --push --all \"<remote>\"",
        "Без сырого вывода в tool log",
        "оба списка должны содержать ровно один и тот же URL",
        "к этой URL не должна применяться ни одна `url.*.insteadOf` или `url.*.pushInsteadOf`",
        "имя `origin` или уже раскрытая URL не исключают повторную подстановку адреса",
        "destination должен быть без встроенного пароля или token",
        "настройте credential-free destination",
        "staged tree из `git write-tree`",
        "git ls-remote --heads \"<destination>\" \"<base-full-ref>\" \"<target-full-ref>\"",
        "\"<approved-push-destination>\"",
        "OID base и target либо подтверждённое отсутствие target",
        "при существующем target OID HEAD должен точно совпадать с OID target",
        "при отсутствии target OID HEAD должен точно совпадать с OID base",
        "пересоберите кандидата от точного удалённого состояния",
        "если существует `MERGE_HEAD`, он должен содержать ровно один OID",
        "совпадающий с OID base",
        "Дополнительные merge parents требуют пересборки",
        "HEAD как первого будущего parent",
        "все OID из него как остальных будущих parents",
        "ожидаемый merge-base base и будущего commit",
        "для обычного commit",
        "для merge с base среди `MERGE_HEAD`",
        "Merge без base среди будущих parents этим правилом не публикуйте",
        "точный снимок будущих метаданных commit",
        "сообщение побайтово",
        "author и committer с name, email, date и timezone",
        "сообщение побайтово, включая trailers",
        "режим подписи и полный ожидаемый набор headers с их значениями",
        "Не подменяйте этот снимок текущими значениями Git config",
        "требует отдельного показа и нового одобрения после создания, но до push",
        "Покажите пользователю этот снимок метаданных",
        "git diff --cached <expected-merge-base-oid> --",
        "git diff --cached <target-oid> --",
        "tree diff не доказывает отсутствие промежуточной неопубликованной истории",
        "не заменяет точное совпадение HEAD с target или base",
        "Непосредственно перед `commit`",
        "сравните все зафиксированные значения",
        "полный список будущих parents",
        "метаданные commit",
        "Только после успешного сравнения создайте commit из одобренных значений",
        "явно передайте точные bytes сообщения",
        "author/committer identities, timestamps/timezones",
        "не оставляйте их Git config или текущему времени",
        "режим границы",
        "destination и отсутствие URL-подстановок",
        "Ошибка обновления или любое изменение запрещает `commit`, `push`, создание и обновление PR",
        "упорядоченный список его parents — с одобренным списком",
        "merge-base base и commit — с ожидаемым merge-base",
        "не выводя неожиданные raw metadata в tool log",
        "git cat-file commit \"<verified-commit-oid>\"",
        "побайтово сравните его headers и сообщение с одобренным снимком",
        "Любой дополнительный header",
        "внесённое hook-ом",
        "делает commit новым кандидатом",
        "Перед `push` снова сравните destination и отсутствие URL-подстановок",
        "перечитайте с него base/target",
        "\"<verified-commit-oid>:refs/heads/<target>\"",
        "\"--force-with-lease=refs/heads/<target>:<approved-target-oid>\"",
        "\"--force-with-lease=refs/heads/<target>:\"",
        "пустой expect требует его отсутствия",
        "lease — только server-side CAS для обновляемого target ref",
        "сам по себе может разрешить non-fast-forward",
        "gates обязаны отдельно доказать нужную ancestry",
        "no-op refspec для base не создают server-side cross-ref CAS",
        "остановитесь до push, пока не доказан такой серверный guard",
        "Только в заранее одобренном режиме `target-only`",
        "После `push`, но до работы с PR, прямым `git ls-remote` с одобренного destination",
        "OID target — указывать ровно на этот commit",
        "имена head/base PR должны совпасть с ожидаемыми ветками",
        "OID head PR должен совпасть с проверенным OID target",
        "OID base PR не заменяет повторную проверку живого OID удалённой base",
        "получите новое одобрение",
    ):
        assert invariant in section

    approval_index = section.index("Получите явное одобрение")
    for preapproval_gate in (
        "выбранный до одобрения режим границы",
        "git remote get-url --push --all \"<remote>\"",
        "git ls-remote --heads \"<destination>\" \"<base-full-ref>\" \"<target-full-ref>\"",
        "при существующем target OID HEAD должен точно совпадать с OID target",
        "если существует `MERGE_HEAD`, он должен содержать ровно один OID",
        "точный снимок будущих метаданных commit",
        "git diff --cached <expected-merge-base-oid> --",
    ):
        assert section.index(preapproval_gate) < approval_index

    precommit_check_index = section.index("Непосредственно перед `commit`")
    stop_index = section.index("Ошибка обновления или любое изменение запрещает `commit`")
    commit_creation_index = section.index(
        "Только после успешного сравнения создайте commit из одобренных значений"
    )
    metadata_check_index = section.index('git cat-file commit "<verified-commit-oid>"')
    push_index = section.index("Push выполняйте")
    assert (
        approval_index
        < precommit_check_index
        < stop_index
        < commit_creation_index
        < metadata_check_index
        < push_index
    )

    assert "<approved-commit-oid>" not in section
    assert section.count('"--force-with-lease=refs/heads/<target>:') == 2


def test_late_base_gate_runs_after_tests_before_commit_and_push() -> None:
    body = SKILL.read_text(encoding="utf-8")
    pr_mode = body.split("## Режим 1: local-wip-to-clean-pr", 1)[1].split(
        "## Режим 2: post-merge-branch-housekeeping", 1
    )[0]
    normalized = " ".join(pr_mode.split())

    tests_at = pr_mode.index("6. Привяжите проверки")
    late_gate_at = pr_mode.index("7. После тестов выполните поздний гейт базы")
    commit_at = pr_mode.index("8. Сформируйте commit")
    pre_push_gate_at = pr_mode.index(
        "9. Непосредственно перед push выполните короткий гейт"
    )
    push_at = pr_mode.index("10. Push:")
    post_push_at = pr_mode.index("11. После push, но до PR")
    pr_at = pr_mode.index("12. Откройте PR")

    assert (
        tests_at
        < late_gate_at
        < commit_at
        < pre_push_gate_at
        < push_at
        < post_push_at
        < pr_at
    )

    for invariant in (
        "разделите clean committed-only состояние и WIP",
        "status, включая untracked",
        "не продолжайте автоматически при mixed WIP",
        "смешаны нужные и чужие hunks",
        "clean committed-only переносите без stash",
        "WIP — только по fail-closed процедуре",
        "tested_tree=$(git -C <repo> write-tree)",
        "после каждого первоначального или повторного test run",
        "до commit, сохраните `verified_base_sha`",
        "Codex plugin явно пересчитайте semver относительно нового `origin/main`",
        "сохранив выбранный до drift тип повышения",
        "отсутствие tracked изменений вне index, untracked и unmerged",
        "сохраните `verified_head_sha`",
        "заново найдите его текущий selector по сохранённым object SHA и subject",
        "не выполняйте cleanup без исключительного контроля над stash reflog",
        "HEAD и tree должны равняться `verified_head_sha` и `tested_tree`",
        "--force-with-lease=refs/heads/<branch>:<expected_remote_sha>",
        "снова получите `origin/main` и точный remote head",
        "base drift возвращает процесс к rebase и повторным тестам",
        "remote head, не равный `verified_head_sha`, останавливает процесс",
    ):
        assert invariant in normalized


def test_recovery_contract_is_fail_closed_and_identity_based() -> None:
    recovery = RECOVERY.read_text(encoding="utf-8")
    normalized = " ".join(recovery.split())

    for invariant in (
        "Поток A: Чистое Committed-Only Состояние",
        "Recovery-stash здесь не создаётся",
        "все staged, unstaged и untracked пути",
        "это mixed WIP: не создавайте stash, не запускайте rebase",
        "Неразделимые same-path изменения тоже считаются mixed WIP",
        "INTENDED_PATH_SCOPE_PASS",
        'test "${hunk_scope_state:-UNPROVEN}" = INTENDED_HUNKS_ONLY',
        "STABLE_SCOPE_PASS",
        "# STABLE_SCOPE_GATE_BEGIN",
        "# STABLE_SCOPE_GATE_END",
        "в точности равняться всему `intended_paths` за вычетом manifest",
        'if ! initial_unmerged=$(git -C "$repo" ls-files -u); then',
        "появилось ровно одно новое значение `%H`",
        'if ! test "$recovery_stash_count" = 1; then',
        "Не получайте его через `stash@{0}`",
        "точный subject новой записи",
        "успешный no-op `stash push` не создаёт запись",
        "точное дерево staged WIP до stash",
        "канонического JSON без поля `version`",
        "base-derived поля",
        "intended-версия точно равна следующему semver этого типа",
        "intended_index_tree",
        'test "$intended_index_tree" = "$tested_tree"',
        '"${recovery_stash_sha}^2^1"',
        '"${recovery_stash_sha}^2^{tree}"',
        '"${recovery_stash_sha}^{tree}"',
        "отдельный `GIT_INDEX_FILE`",
        "--binary --full-index --unified=8 --no-renames",
        "apply.ignoreWhitespace=false",
        "--cached -C8 --whitespace=nowarn --quiet -",
        "expected_tree",
        "actual_tree",
        'if ((${#stable_paths[@]} == 0)); then',
        "expected_tree=NOT_REQUIRED",
        "UNIQUE_HUNK_MAPPING_PASS",
        "AMBIGUOUS_HUNK_MAPPING",
        "# UNIQUE_HUNK_VERIFIER_BEGIN",
        "# UNIQUE_HUNK_VERIFIER_END",
        "не перечитывайте verifier из worktree после stash",
        '"$repo" "$old_head_sha" "$new_head_sha" "$recovery_stash_sha"',
        '"${stable_paths[@]}" <<\'PY\'',
        "unique_hunk_mapping=AMBIGUOUS_HUNK_MAPPING",
        'test -n "$unique_hunk_mapping"',
        'case "$unique_hunk_mapping" in',
        "NOT_REQUIRED|UNIQUE_HUNK_MAPPING_PASS",
        'if ! test "$pre_apply_head_sha" = "$new_head_sha"; then',
        "оба могут одинаково перенести правку на новую",
        "сами по себе не доказывают положение среди повторяющихся",
        "if ! expected_index_dir=$(mktemp -d); then",
        'expected_index_path="${expected_index_dir:?}/index"',
        'test ! -e "$expected_index_path"',
        "успешный exit status",
        "object ID частичного результата тоже может быть непустым",
        "Ошибка любого звена pipeline",
        "status, включая untracked, обязан быть пуст",
        'if ! git -C "$repo" rebase origin/main; then',
        'if ! git -C "$repo" stash apply "$recovery_stash_sha"; then',
        "`apply --index` ложно конфликтным",
        "base-derived manifest может временно отсутствовать",
        "APPLIED_SCOPE_PASS",
        "все `stable_paths`",
        "полному `intended_paths`",
        "SEMVER_RECALC_PASS",
        "STAGED_SCOPE_PASS",
        '"$expected_tree" "$actual_tree" -- "${stable_paths[@]}"',
        "`version_bump_kind`",
        "следующему `patch`, `minor` или `major` semver того же сохранённого типа",
        "commit запрещён: stash сохраняется",
        "Сразу после каждого первоначального или повторного test run",
        "verified_base_sha` появляется только после успешных compare и ancestry",
        'if ! current_base_sha=$(git -C "$repo" rev-parse origin/main); then',
        'if ! test "$current_base_sha" = "$tested_base_sha"; then',
        'if ! git -C "$repo" merge-base --is-ancestor "$current_base_sha" HEAD; then',
        "пересчитайте версию `plugins/team-skills/.codex-plugin/plugin.json`",
        'if ! current_index_tree=$(git -C "$repo" write-tree); then',
        'if ! test "$current_index_tree" = "$tested_tree"; then',
        "git -C \"$repo\" diff --quiet",
        'if ! untracked_paths=$(git -C "$repo" ls-files --others --exclude-standard); then',
        'if ! unmerged_entries=$(git -C "$repo" ls-files -u); then',
        "git -C \"$repo\" ls-files -u",
        "verified_head_sha` содержит ровно `tested_tree`",
        'if ! committed_tree_sha=$(',
        'if ! test "$committed_tree_sha" = "$tested_tree"; then',
        'if ! committed_status=$(',
        "Удалить Только Созданный Процессом Stash",
        'test "${stash_reflog_exclusive_state:-UNPROVEN}" =',
        "if ! drop_candidate_sha=$( git -C \"$repo\" rev-parse \"$recovery_stash_ref\" ); then",
        "git -C \"$repo\" stash drop \"$recovery_stash_ref\"",
        'if ! git -C "$repo" stash drop "$recovery_stash_ref"; then',
        'if ! cmp -s "$stash_before_path" "$stash_after_path"; then',
        "исключительном контроле процесса над stash reflog",
        "текущий `HEAD == verified_head_sha`",
        "текущий `HEAD^{tree} == tested_tree`",
        'if ! pre_push_base_sha=$(git -C "$repo" rev-parse origin/main); then',
        'if ! test "$pre_push_base_sha" = "$verified_base_sha"; then',
        'if ! pre_push_head_sha=$(git -C "$repo" rev-parse HEAD); then',
        'if ! test "$pre_push_head_sha" = "$verified_head_sha"; then',
        'if ! pre_push_tree_sha=$(git -C "$repo" rev-parse \'HEAD^{tree}\'); then',
        'if ! test "$pre_push_tree_sha" = "$tested_tree"; then',
        'if ! pre_push_status=$(',
        'if ! git -C "$repo" push origin "HEAD:refs/heads/$branch"',
        "--force-with-lease=refs/heads/<branch>:<expected_remote_sha>",
        "Readback После Push, До PR",
        'if ! git -C "$repo" fetch origin --prune; then',
        'if ! post_push_base_sha=$(git -C "$repo" rev-parse origin/main); then',
        "if ! post_push_head_sha=$(",
        "if ! post_push_head_count=$(",
        'if ! test "$post_push_head_count" = 1; then',
        'if ! test "$post_push_head_sha" = "$verified_head_sha"; then',
        'if ! test "$post_push_base_sha" = "$verified_base_sha"; then',
        "post_push_base_sha=$(git -C \"$repo\" rev-parse origin/main)",
        "test \"$post_push_head_sha\" = \"$verified_head_sha\"",
        "origin/main` продвинулся",
    ):
        assert invariant in normalized

    assert "rev-parse 'stash@{0}'" not in recovery
    assert 'rev-parse "stash@{0}"' not in recovery
    assert "normalize_wip_diff" not in recovery
    assert "logical_wip_fingerprint" not in recovery
    assert recovery.count("# UNIQUE_HUNK_VERIFIER_BEGIN") == 1
    assert recovery.count("# UNIQUE_HUNK_VERIFIER_END") == 1
    assert recovery.count("# STABLE_SCOPE_GATE_BEGIN") == 1
    assert recovery.count("# STABLE_SCOPE_GATE_END") == 1
    assert _unique_hunk_verifier_source().strip().startswith("import os")
    assert "stash drop \"$recovery_stash_ref\"" in recovery
    stable_gate_at = recovery.index("# STABLE_SCOPE_GATE_END")
    unique_paths_at = recovery.index(
        'if ((${#stable_paths[@]} == 0)); then', stable_gate_at
    )
    unique_mapping_at = recovery.index("UNIQUE_HUNK_MAPPING_PASS", unique_paths_at)
    stash_apply_at = recovery.index(
        'git -C "$repo" stash apply "$recovery_stash_sha"', unique_mapping_at
    )
    expected_paths_at = recovery.index(
        'if ((${#stable_paths[@]} == 0)); then', unique_paths_at + 1
    )
    assert (
        stable_gate_at
        < unique_paths_at
        < unique_mapping_at
        < stash_apply_at
        < expected_paths_at
    )


def test_recovery_reference_initializes_shared_inputs_and_scopes_optional_gates() -> None:
    recovery = RECOVERY.read_text(encoding="utf-8")

    common_at = recovery.index("## Общие Доказательства")
    branch_at = recovery.index('if ! branch=$(git -C "$repo" branch --show-current); then')
    flow_a_at = recovery.index("## Поток A: Чистое Committed-Only Состояние")
    flow_b_at = recovery.index("## Поток B: WIP Через Recovery-Stash")
    assert common_at < branch_at < flow_a_at < flow_b_at
    assert recovery.count(
        'if ! branch=$(git -C "$repo" branch --show-current); then'
    ) == 1

    plugin_scope_at = recovery.index("if ! plugin_scope_state=$(python3 -c '")
    stable_scope_at = recovery.index("# STABLE_SCOPE_GATE_BEGIN", plugin_scope_at)
    first_mutation_at = recovery.index('if ! git -C "$repo" add -A; then')
    assert flow_b_at < plugin_scope_at < stable_scope_at < first_mutation_at
    for invariant in (
        'path.startswith("plugins/team-skills/")',
        'elif manifest not in paths:',
        'print("PLUGIN_CHANGE")',
        'print("NO_PLUGIN_CHANGE")',
        'case "$plugin_scope_state" in',
        'if stable != intended - allowed_derived:',
        'if plugin_state == "PLUGIN_CHANGE":',
        'elif plugin_state == "NO_PLUGIN_CHANGE":',
        "manifest_payload_fingerprint=NOT_REQUIRED",
        "base_plugin_version=NOT_REQUIRED",
        "# PLUGIN_SEMVER_GATE_BEGIN",
        "semver_recalc_state=NOT_REQUIRED",
        "# PLUGIN_SEMVER_GATE_END",
    ):
        assert invariant in recovery
    assert recovery.count('case "$plugin_scope_state" in') >= 4

    semver_begin_at = recovery.index("# PLUGIN_SEMVER_GATE_BEGIN")
    manifest_add_at = recovery.index(
        'git -C "$repo" add -- "$manifest_relative_path"', semver_begin_at
    )
    no_plugin_semver_at = recovery.index(
        "semver_recalc_state=NOT_REQUIRED", manifest_add_at
    )
    semver_end_at = recovery.index("# PLUGIN_SEMVER_GATE_END", no_plugin_semver_at)
    staged_scope_at = recovery.index("STAGED_SCOPE_PASS", semver_end_at)
    assert (
        semver_begin_at
        < manifest_add_at
        < no_plugin_semver_at
        < semver_end_at
        < staged_scope_at
    )

    cleanup_at = recovery.index("### 3. Удалить Только Созданный Процессом Stash")
    lookup_at = recovery.index("if ! recovery_stash_ref=$(", cleanup_at)
    lookup_count_at = recovery.index("recovery_stash_ref_count", lookup_at)
    resolve_at = recovery.index(
        'git -C "$repo" rev-parse "$recovery_stash_ref"', lookup_count_at
    )
    drop_at = recovery.index(
        'git -C "$repo" stash drop "$recovery_stash_ref"', resolve_at
    )
    assert cleanup_at < lookup_at < lookup_count_at < resolve_at < drop_at
    assert '-v sha="$recovery_stash_sha"' in recovery[lookup_at:resolve_at]
    assert '-v subject="$expected_stash_subject"' in recovery[lookup_at:resolve_at]
    assert 'test "$recovery_stash_ref_count" = 1' in recovery[lookup_at:resolve_at]


def test_stable_scope_gate_rejects_omissions_before_downstream_consumers() -> None:
    manifest = "plugins/team-skills/.codex-plugin/plugin.json"
    intended_plugin = ["src/change.py", "tests/test_change.py", manifest]

    exact_plugin = _run_stable_scope_gate(
        "PLUGIN_CHANGE",
        ["src/change.py", "tests/test_change.py"],
        intended_plugin,
    )
    assert exact_plugin.returncode == 0, exact_plugin.stderr
    assert exact_plugin.stdout == "DOWNSTREAM_REACHED\n"

    for plugin_state, stable_paths, intended_paths in (
        ("PLUGIN_CHANGE", ["src/change.py"], intended_plugin),
        (
            "PLUGIN_CHANGE",
            ["src/change.py", "tests/test_change.py", manifest],
            intended_plugin,
        ),
        ("PLUGIN_CHANGE", ["src/change.py"], ["src/change.py"]),
        (
            "NO_PLUGIN_CHANGE",
            ["src/change.py"],
            ["src/change.py", "tests/test_change.py"],
        ),
        (
            "PLUGIN_CHANGE",
            ["src/change.py", "src/change.py", "tests/test_change.py"],
            intended_plugin,
        ),
        (
            "PLUGIN_CHANGE",
            ["src/change.py", "tests/test_change.py"],
            [*intended_plugin, "src/change.py"],
        ),
        ("UNKNOWN", ["src/change.py"], ["src/change.py"]),
    ):
        rejected = _run_stable_scope_gate(
            plugin_state,
            stable_paths,
            intended_paths,
        )
        assert rejected.returncode != 0
        assert rejected.stdout == ""

    exact_non_plugin = _run_stable_scope_gate(
        "NO_PLUGIN_CHANGE",
        ["src/change.py", "tests/test_change.py"],
        ["src/change.py", "tests/test_change.py"],
    )
    assert exact_non_plugin.returncode == 0, exact_non_plugin.stderr
    assert exact_non_plugin.stdout == "DOWNSTREAM_REACHED\n"

    documents = (
        RECOVERY.read_text(encoding="utf-8"),
        (SKILL_DIR / "examples" / "good-04.md").read_text(encoding="utf-8"),
    )
    for document in documents:
        assert document.count("# STABLE_SCOPE_GATE_BEGIN") == 1
        assert document.count("# STABLE_SCOPE_GATE_END") == 1
        gate_at = document.index("# STABLE_SCOPE_GATE_END")
        unique_at = document.index("unique_hunk_mapping=$(", gate_at)
        apply_at = document.index(
            'git -C "$repo" stash apply "$recovery_stash_sha"', unique_at
        )
        expected_at = document.index(
            'if ((${#stable_paths[@]} == 0)); then', apply_at
        )
        assert gate_at < unique_at < apply_at < expected_at


def test_unproven_stash_cleanup_preserves_recovery_and_reaches_prepush(
    tmp_path: Path,
) -> None:
    example = SKILL_DIR / "examples" / "good-04.md"
    source = _recovery_stash_cleanup_source()
    example_source = _recovery_stash_cleanup_source(example)
    unproven_branch = source.rsplit("\nelse\n", 1)[1].split("\nfi\ncase", 1)[0]
    example_unproven_branch = example_source.rsplit("\nelse\n", 1)[1].split(
        "\nfi\ncase", 1
    )[0]
    assert unproven_branch == example_unproven_branch

    repo = _init_repo(tmp_path / "recovery probe;quoted")
    (repo / "tracked.txt").write_text("recovery\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "stash", "push", "-m", "cleanup-probe")
    recovery_sha = _git(repo, "rev-parse", "stash@{0}").stdout.strip()
    head_before = _git(repo, "rev-parse", "HEAD").stdout.strip()
    status_before = _git(repo, "status", "--porcelain=v1").stdout
    stashes_before = _stash_rows(repo)

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    git_call_log = tmp_path / "git-calls.log"
    fake_git = fake_bin / "git"
    fake_git.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$GIT_CALL_LOG\"\nexit 97\n",
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    probe_env = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "GIT_CALL_LOG": str(git_call_log),
    }
    driver = f"""
set -e
recovery_stash_sha=$1
repo=$2
{source}
printf 'PRE_PUSH_REACHED:%s:%s\n' \
  "$recovery_stash_cleanup_state" "$recovery_stash_restore_command"
"""

    result = subprocess.run(
        ["bash", "-c", driver, "cleanup-probe", recovery_sha, str(repo)],
        env=probe_env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert f"Резервный stash сохранён: {recovery_sha}\n" in result.stdout
    prepush_line = next(
        line
        for line in result.stdout.splitlines()
        if line.startswith("PRE_PUSH_REACHED:PRESERVED:")
    )
    restore_command = prepush_line.removeprefix("PRE_PUSH_REACHED:PRESERVED:")
    assert f"Команда восстановления: {restore_command}\n" in result.stdout
    assert f"PRE_PUSH_REACHED:PRESERVED:{restore_command}\n" in result.stdout
    assert "<repo>" not in result.stdout
    assert "Recovery-stash preserved" not in result.stdout
    assert "Restore:" not in result.stdout
    assert not git_call_log.exists()
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == head_before
    assert _git(repo, "status", "--porcelain=v1").stdout == status_before
    assert _stash_rows(repo) == stashes_before

    restored = subprocess.run(
        ["bash", "-c", restore_command],
        check=False,
        capture_output=True,
        text=True,
    )
    assert restored.returncode == 0, restored.stderr
    assert (repo / "tracked.txt").read_text(encoding="utf-8") == "recovery\n"
    assert _stash_rows(repo) == stashes_before
    assert 'if test "${stash_reflog_exclusive_state:-UNPROVEN}" =' in source
    assert 'if ! test "${stash_reflog_exclusive_state:-UNPROVEN}" =' not in source

    documents = (
        RECOVERY.read_text(encoding="utf-8"),
        example.read_text(encoding="utf-8"),
    )
    for document in documents:
        assert document.count("# RECOVERY_STASH_CLEANUP_BEGIN") == 1
        assert document.count("# RECOVERY_STASH_CLEANUP_END") == 1
        cleanup_end_at = document.index("# RECOVERY_STASH_CLEANUP_END")
        prepush_at = document.index(
            'if ! git -C "$repo" fetch origin --prune; then', cleanup_end_at
        )
        assert cleanup_end_at < prepush_at
        preserved_at = document.index(
            "recovery_stash_cleanup_state=PRESERVED", cleanup_end_at - 1200
        )
        assert preserved_at < cleanup_end_at


def test_failed_expected_tree_producer_blocks_after_apply_succeeds(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path / "repo")
    old_head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "tracked.txt").write_text("intended\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "stash", "push", "-m", "pipeline-probe")
    recovery_sha = _git(repo, "rev-parse", "stash@{0}").stdout.strip()
    expected_index = tmp_path / "expected.index"

    result = subprocess.run(
        [
            "bash",
            "-c",
            """
set -o pipefail
GIT_INDEX_FILE="$EXPECTED_INDEX" git -C "$REPO" read-tree HEAD || exit 19
if ! {
  git --literal-pathspecs -C "$REPO" diff \
    --binary --full-index --unified=8 --no-renames \
    --no-color --no-ext-diff --no-textconv \
    "$OLD_HEAD" "${RECOVERY_SHA}^2" -- tracked.txt
  false
} | GIT_INDEX_FILE="$EXPECTED_INDEX" \
    git -C "$REPO" -c apply.ignoreWhitespace=false apply \
      --cached -C8 --whitespace=nowarn --quiet -; then
  exit 23
fi
""",
        ],
        env={
            **os.environ,
            "REPO": str(repo),
            "OLD_HEAD": old_head_sha,
            "RECOVERY_SHA": recovery_sha,
            "EXPECTED_INDEX": str(expected_index),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 23
    assert result.stdout == ""
    temp_env = {**os.environ, "GIT_INDEX_FILE": str(expected_index)}
    applied_tree = subprocess.run(
        ["git", "-C", str(repo), "write-tree"],
        env=temp_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert applied_tree.returncode == 0, applied_tree.stderr
    assert applied_tree.stdout.strip() != _git(
        repo, "rev-parse", "HEAD^{tree}"
    ).stdout.strip()


def test_failed_post_push_producer_cannot_leave_a_valid_head_sha() -> None:
    expected_sha = "6c4e7753e4de36fe69279854f584738a4c1d7d52"
    result = subprocess.run(
        [
            "bash",
            "-c",
            """
set -o pipefail
if ! post_push_head_sha=$( {
  printf '%s\\trefs/heads/feature\\n' "$EXPECTED_SHA"
  false
} | awk 'NF == 2 { print $1 }'); then
  post_push_head_sha=
  exit 23
fi
test "$post_push_head_sha" = "$EXPECTED_SHA"
""",
        ],
        env={**os.environ, "EXPECTED_SHA": expected_sha},
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 23
    assert result.stdout == ""


def test_post_push_head_mismatch_cannot_be_masked_by_true_base_compare() -> None:
    result = subprocess.run(
        [
            "bash",
            "-c",
            """
post_push_head_count=1
post_push_head_sha=wrong-head
verified_head_sha=expected-head
post_push_base_sha=same-base
verified_base_sha=same-base
if ! test "$post_push_head_count" = 1; then
  exit 11
fi
if ! test "$post_push_head_sha" = "$verified_head_sha"; then
  exit 23
fi
if ! test "$post_push_base_sha" = "$verified_base_sha"; then
  exit 24
fi
""",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 23
    assert result.stdout == ""


def test_late_base_drift_cannot_be_masked_by_verified_assignment() -> None:
    result = subprocess.run(
        [
            "bash",
            "-c",
            """
tested_base_sha=old-base
current_base_sha=new-base
verified_base_sha=
if ! test "$current_base_sha" = "$tested_base_sha"; then
  exit 21
fi
if ! test ancestor = ancestor; then
  exit 22
fi
verified_base_sha="$current_base_sha"
printf '%s\n' "$verified_base_sha"
""",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 21
    assert result.stdout == ""


def test_tested_tree_mismatch_cannot_be_masked_by_clean_scope() -> None:
    result = subprocess.run(
        [
            "bash",
            "-c",
            """
current_index_tree=changed-tree
tested_tree=tested-tree
untracked_paths=
unmerged_entries=
if ! test "$current_index_tree" = "$tested_tree"; then
  exit 31
fi
if ! true; then
  exit 32
fi
if ! test -z "$untracked_paths"; then
  exit 33
fi
if ! test -z "$unmerged_entries"; then
  exit 34
fi
printf 'commit-ran\n'
""",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 31
    assert result.stdout == ""


@pytest.mark.parametrize(
    ("pre_push_base_sha", "pre_push_head_sha", "pre_push_tree_sha", "status", "code"),
    [
        ("new-base", "same-head", "same-tree", "", 41),
        ("same-base", "new-head", "same-tree", "", 43),
        ("same-base", "same-head", "new-tree", "", 44),
        ("same-base", "same-head", "same-tree", "dirty", 45),
    ],
)
def test_pre_push_mismatch_cannot_be_masked_by_later_success(
    pre_push_base_sha: str,
    pre_push_head_sha: str,
    pre_push_tree_sha: str,
    status: str,
    code: int,
) -> None:
    result = subprocess.run(
        [
            "bash",
            "-c",
            """
verified_base_sha=same-base
verified_head_sha=same-head
tested_tree=same-tree
if ! test "$PRE_PUSH_BASE_SHA" = "$verified_base_sha"; then
  exit 41
fi
if ! test ancestor = ancestor; then
  exit 42
fi
if ! test "$PRE_PUSH_HEAD_SHA" = "$verified_head_sha"; then
  exit 43
fi
if ! test "$PRE_PUSH_TREE_SHA" = "$tested_tree"; then
  exit 44
fi
if ! test -z "$PRE_PUSH_STATUS"; then
  exit 45
fi
printf 'push-ran\n'
""",
        ],
        env={
            **os.environ,
            "PRE_PUSH_BASE_SHA": pre_push_base_sha,
            "PRE_PUSH_HEAD_SHA": pre_push_head_sha,
            "PRE_PUSH_TREE_SHA": pre_push_tree_sha,
            "PRE_PUSH_STATUS": status,
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == code
    assert result.stdout == ""


def test_documented_pytest_run_is_bound_to_target_repo(tmp_path: Path) -> None:
    target_repo = tmp_path / "target repo"
    caller_dir = tmp_path / "caller"
    target_repo.mkdir()
    caller_dir.mkdir()

    result = subprocess.run(
        [
            "bash",
            "-c",
            """
repo="$TARGET_REPO"
if ! (cd -- "$repo" && "$PYTHON_BIN" -c '
import os, pathlib, sys
actual = pathlib.Path.cwd().resolve()
expected = pathlib.Path(os.environ["TARGET_REPO"]).resolve()
raise SystemExit(0 if actual == expected else 1)
'); then
  exit 23
fi
""",
        ],
        cwd=caller_dir,
        env={
            **os.environ,
            "PYTHON_BIN": sys.executable,
            "TARGET_REPO": str(target_repo),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    example = (SKILL_DIR / "examples" / "good-04.md").read_text(encoding="utf-8")
    assert example.count('(cd -- "$repo" && python -m pytest)') == 2


def test_base_plugin_version_is_read_from_exact_tested_base(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path / "repo")
    manifest = repo / "plugins/team-skills/.codex-plugin/plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps({"name": "team-skills", "version": "1.2.3"}) + "\n",
        encoding="utf-8",
    )
    _git(repo, "add", str(manifest.relative_to(repo)))
    _git(repo, "commit", "-qm", "add manifest")
    tested_base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    result = subprocess.run(
        [
            "bash",
            "-c",
            """
set -o pipefail
base_plugin_version=stale-value
if ! base_plugin_version=$(git -C "$REPO" show \
  "$TESTED_BASE_SHA:plugins/team-skills/.codex-plugin/plugin.json" \
  | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["version"])'); then
  base_plugin_version=
  exit 23
fi
printf '%s\n' "$base_plugin_version"
""",
        ],
        env={
            **os.environ,
            "PYTHON_BIN": sys.executable,
            "REPO": str(repo),
            "TESTED_BASE_SHA": tested_base_sha,
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "1.2.3\n"
    recovery = RECOVERY.read_text(encoding="utf-8")
    example = (SKILL_DIR / "examples" / "good-04.md").read_text(encoding="utf-8")
    exact_source = (
        '"$tested_base_sha:plugins/team-skills/.codex-plugin/plugin.json"'
    )
    assert exact_source in recovery
    assert exact_source in example
    assert "origin/main:plugins/team-skills/.codex-plugin/plugin.json" not in recovery
    assert "origin/main:plugins/team-skills/.codex-plugin/plugin.json" not in example


def test_empty_stable_paths_have_an_explicit_no_diff_branch() -> None:
    documents = (
        RECOVERY.read_text(encoding="utf-8"),
        (SKILL_DIR / "examples" / "good-04.md").read_text(encoding="utf-8"),
    )

    for document in documents:
        empty_at = document.index('if ((${#stable_paths[@]} == 0)); then')
        not_required_at = document.index("expected_tree=NOT_REQUIRED", empty_at)
        else_at = document.index("\nelse\n", not_required_at)
        expected_index_at = document.index(
            "if ! expected_index_dir=$(mktemp -d); then", else_at
        )
        branch_end_at = document.index(
            "# EMPTY_STABLE_PATHS_BRANCH_END", expected_index_at
        )
        semver_at = document.index("SEMVER_RECALC_PASS", branch_end_at)
        staged_scope_at = document.index("STAGED_SCOPE_PASS", semver_at)
        assert (
            empty_at
            < not_required_at
            < else_at
            < expected_index_at
            < branch_end_at
            < semver_at
            < staged_scope_at
        )


def test_initial_unmerged_path_blocks_before_index_mutation(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path / "repo")
    _git(repo, "switch", "-qc", "feature")
    (repo / "tracked.txt").write_text("feature\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "feature change")
    _git(repo, "switch", "main")
    (repo / "tracked.txt").write_text("main\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "main change")
    merge = _git(repo, "merge", "feature", check=False)
    assert merge.returncode != 0

    unmerged_before = _git(repo, "ls-files", "-u").stdout
    index_before = _git(repo, "ls-files", "-s").stdout
    stashes_before = _stash_rows(repo)
    assert unmerged_before

    result = subprocess.run(
        [
            "bash",
            "-c",
            """
if ! initial_unmerged=$(git -C "$REPO" ls-files -u); then
  initial_unmerged=
  exit 22
fi
if ! test -z "$initial_unmerged"; then
  exit 23
fi
git -C "$REPO" add -A
printf 'mutation-ran\n'
""",
        ],
        env={**os.environ, "REPO": str(repo)},
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 23
    assert result.stdout == ""
    assert _git(repo, "ls-files", "-u").stdout == unmerged_before
    assert _git(repo, "ls-files", "-s").stdout == index_before
    assert _stash_rows(repo) == stashes_before


def test_self_updated_verifier_runs_from_recovery_stash_blob(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path / "repo")
    verifier_path = (
        "plugins/team-skills/skills/git-pr-lifecycle-safeguard/"
        "references/late-base-gate.md"
    )
    verifier_file = repo / verifier_path
    verifier_file.parent.mkdir(parents=True)
    verifier_file.write_text("old reference without verifier\n", encoding="utf-8")
    _git(repo, "add", verifier_path)
    _git(repo, "commit", "-qm", "old verifier reference")
    _git(repo, "switch", "-qc", "feature")

    old_head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    verifier_file.write_text(RECOVERY.read_text(encoding="utf-8"), encoding="utf-8")
    _git(repo, "add", verifier_path)
    intended_index_tree = _git(repo, "write-tree").stdout.strip()
    _git(repo, "stash", "push", "-m", "self-update-verifier-probe")
    recovery_sha = _git(repo, "rev-parse", "stash@{0}").stdout.strip()
    _assert_stash_captured_index(
        repo, recovery_sha, old_head_sha, intended_index_tree
    )

    _git(repo, "switch", "main")
    (repo / "base-only.txt").write_text("new base\n", encoding="utf-8")
    _git(repo, "add", "base-only.txt")
    _git(repo, "commit", "-qm", "advance base")
    _git(repo, "switch", "feature")
    _git(repo, "rebase", "main")
    new_head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    assert "# UNIQUE_HUNK_VERIFIER_BEGIN" not in verifier_file.read_text(
        encoding="utf-8"
    )
    verifier_blob_sha, verifier_source = (
        _unique_hunk_verifier_source_from_revision(
            repo,
            f"{recovery_sha}^2",
            verifier_path,
        )
    )
    assert verifier_blob_sha == _git(
        repo, "rev-parse", f"{recovery_sha}^2:{verifier_path}"
    ).stdout.strip()
    assert verifier_source == _unique_hunk_verifier_source()
    assert (
        _unique_hunk_mapping_status(
            repo,
            old_head_sha,
            new_head_sha,
            recovery_sha,
            [verifier_path],
            source=verifier_source,
        )
        == "NOT_REQUIRED"
    )
    assert recovery_sha in {row.split("\t", 1)[0] for row in _stash_rows(repo)}


def test_expected_tree_survives_nonconflicting_same_file_base_drift(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path / "repo")
    tracked = repo / "tracked.txt"
    base_lines = [f"line {index}\n" for index in range(1, 21)]
    tracked.write_text("".join(base_lines), encoding="utf-8")
    _git(repo, "commit", "-qam", "expand base")
    _git(repo, "switch", "-qc", "feature")
    (repo / "feature-committed.txt").write_text("feature\n", encoding="utf-8")
    _git(repo, "add", "feature-committed.txt")
    _git(repo, "commit", "-qm", "feature commit before WIP")

    old_head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    feature_lines = base_lines.copy()
    feature_lines[-2] = "feature line 19\n"
    tracked.write_text("".join(feature_lines), encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    intended_index_tree = _git(repo, "write-tree").stdout.strip()
    raw_before = _raw_wip_fingerprint(repo, old_head_sha, ["tracked.txt"])
    _git(repo, "stash", "push", "-m", "same-file-probe")
    recovery_sha = _git(repo, "rev-parse", "stash@{0}").stdout.strip()
    _assert_stash_captured_index(
        repo, recovery_sha, old_head_sha, intended_index_tree
    )

    _git(repo, "switch", "main")
    main_lines = base_lines.copy()
    main_lines[1] = "main line 2\n"
    tracked.write_text("".join(main_lines), encoding="utf-8")
    _git(repo, "commit", "-qam", "advance separate hunk")
    new_base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    _git(repo, "switch", "feature")
    _git(repo, "rebase", "main")
    new_head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    assert new_head_sha != new_base_sha
    assert (
        _unique_hunk_mapping_status(
            repo,
            old_head_sha,
            new_head_sha,
            recovery_sha,
            ["tracked.txt"],
        )
        == "UNIQUE_HUNK_MAPPING_PASS"
    )
    apply_result = _git(repo, "stash", "apply", recovery_sha, check=False)
    assert apply_result.returncode == 0, apply_result.stderr
    _git(repo, "add", "tracked.txt")

    actual_tree = _git(repo, "write-tree").stdout.strip()
    expected_tree = _expected_tree_from_stash(
        repo,
        old_head_sha,
        recovery_sha,
        new_head_sha,
        ["tracked.txt"],
        tmp_path / "expected.index",
    )
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == new_head_sha
    assert _git(repo, "write-tree").stdout.strip() == actual_tree
    raw_after = _raw_wip_fingerprint(repo, "HEAD", ["tracked.txt"])
    assert raw_after != raw_before
    assert _trees_match_paths(repo, expected_tree, actual_tree, ["tracked.txt"])
    recovered_lines = tracked.read_text(encoding="utf-8").splitlines()
    assert recovered_lines[1] == "main line 2"
    assert recovered_lines[-2] == "feature line 19"


def test_expected_tree_rejects_same_text_changed_at_wrong_location(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path / "repo")
    tracked = repo / "tracked.txt"
    tracked.write_text("same\nsame\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "repeated lines")
    _git(repo, "switch", "-qc", "feature")

    old_head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    tracked.write_text("changed\nsame\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    intended_index_tree = _git(repo, "write-tree").stdout.strip()
    _git(repo, "stash", "push", "-m", "repeated-line-probe")
    recovery_sha = _git(repo, "rev-parse", "stash@{0}").stdout.strip()
    _assert_stash_captured_index(
        repo, recovery_sha, old_head_sha, intended_index_tree
    )

    _git(repo, "switch", "main")
    (repo / "base-only.txt").write_text("advanced\n", encoding="utf-8")
    _git(repo, "add", "base-only.txt")
    _git(repo, "commit", "-qm", "advance base")
    _git(repo, "switch", "feature")
    _git(repo, "rebase", "main")
    new_head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    expected_tree = _expected_tree_from_stash(
        repo,
        old_head_sha,
        recovery_sha,
        new_head_sha,
        ["tracked.txt"],
        tmp_path / "expected.index",
    )
    tracked.write_text("same\nchanged\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    actual_tree = _git(repo, "write-tree").stdout.strip()

    assert not _trees_match_paths(
        repo, expected_tree, actual_tree, ["tracked.txt"]
    )
    assert recovery_sha in {row.split("\t", 1)[0] for row in _stash_rows(repo)}


def test_unique_hunk_gate_blocks_ambiguous_repeated_line_base_drift(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path / "repo")
    tracked = repo / "tracked.txt"
    base_lines = [
        *(f"U{index}\n" for index in range(1, 10)),
        "same\n",
        "same\n",
        *(f"V{index}\n" for index in range(1, 10)),
    ]
    tracked.write_text("".join(base_lines), encoding="utf-8")
    _git(repo, "commit", "-qam", "ambiguous base")
    _git(repo, "switch", "-qc", "feature")
    (repo / "feature-committed.txt").write_text("feature\n", encoding="utf-8")
    _git(repo, "add", "feature-committed.txt")
    _git(repo, "commit", "-qm", "feature commit before WIP")

    old_head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    intended_lines = base_lines.copy()
    intended_lines[9] = "changed\n"
    tracked.write_text("".join(intended_lines), encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    intended_index_tree = _git(repo, "write-tree").stdout.strip()
    _git(repo, "stash", "push", "-m", "ambiguous-line-probe")
    recovery_sha = _git(repo, "rev-parse", "stash@{0}").stdout.strip()
    _assert_stash_captured_index(
        repo, recovery_sha, old_head_sha, intended_index_tree
    )

    _git(repo, "switch", "main")
    drifted_lines = base_lines.copy()
    drifted_lines.insert(9, "same\n")
    tracked.write_text("".join(drifted_lines), encoding="utf-8")
    _git(repo, "commit", "-qam", "insert ambiguous repeated line")
    new_base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "switch", "feature")
    _git(repo, "rebase", "main")
    new_head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    assert new_head_sha != new_base_sha

    assert _unique_hunk_mapping_status(
        repo,
        old_head_sha,
        new_head_sha,
        recovery_sha,
        ["tracked.txt"],
    ) == "AMBIGUOUS_HUNK_MAPPING"
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == new_head_sha
    assert not _git(
        repo, "status", "--porcelain=v1", "--untracked-files=all"
    ).stdout
    assert recovery_sha in {row.split("\t", 1)[0] for row in _stash_rows(repo)}


def test_unique_hunk_gate_blocks_mode_only_same_path_base_drift(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path / "repo")
    tracked = repo / "tracked.txt"
    tracked.write_text("first\nsecond\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "text base")
    _git(repo, "switch", "-qc", "feature")
    (repo / "feature-committed.txt").write_text("feature\n", encoding="utf-8")
    _git(repo, "add", "feature-committed.txt")
    _git(repo, "commit", "-qm", "feature commit before WIP")

    old_head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    tracked.write_text("first changed\nsecond\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    intended_index_tree = _git(repo, "write-tree").stdout.strip()
    _git(repo, "stash", "push", "-m", "mode-only-drift-probe")
    recovery_sha = _git(repo, "rev-parse", "stash@{0}").stdout.strip()
    _assert_stash_captured_index(
        repo, recovery_sha, old_head_sha, intended_index_tree
    )

    _git(repo, "switch", "main")
    tracked.chmod(0o755)
    _git(repo, "update-index", "--chmod=+x", "tracked.txt")
    _git(repo, "commit", "-qm", "advance base mode only")
    new_base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "switch", "feature")
    _git(repo, "rebase", "main")
    new_head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    assert new_head_sha != new_base_sha

    assert _unique_hunk_mapping_status(
        repo,
        old_head_sha,
        new_head_sha,
        recovery_sha,
        ["tracked.txt"],
    ) == "AMBIGUOUS_HUNK_MAPPING"
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == new_head_sha
    assert not _git(
        repo, "status", "--porcelain=v1", "--untracked-files=all"
    ).stdout
    assert recovery_sha in {row.split("\t", 1)[0] for row in _stash_rows(repo)}


def test_unique_hunk_gate_uses_git_lf_lines_for_control_bytes(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path / "repo")
    tracked = repo / "tracked.txt"
    tracked.write_bytes(b"ANCHOR\r+TAIL\n")
    _git(repo, "commit", "-qam", "control byte base")
    _git(repo, "switch", "-qc", "feature")
    (repo / "feature-committed.txt").write_text("feature\n", encoding="utf-8")
    _git(repo, "add", "feature-committed.txt")
    _git(repo, "commit", "-qm", "feature commit before WIP")

    old_head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    tracked.write_bytes(b"WIPANCHOR\r+TAIL\n")
    _git(repo, "add", "tracked.txt")
    intended_index_tree = _git(repo, "write-tree").stdout.strip()
    _git(repo, "stash", "push", "-m", "control-byte-probe")
    recovery_sha = _git(repo, "rev-parse", "stash@{0}").stdout.strip()
    _assert_stash_captured_index(
        repo, recovery_sha, old_head_sha, intended_index_tree
    )

    _git(repo, "switch", "main")
    tracked.write_bytes(b"ANCHOR\r+BASE\n")
    _git(repo, "commit", "-qam", "advance same Git line after CR")
    new_base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "switch", "feature")
    _git(repo, "rebase", "main")
    new_head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    assert new_head_sha != new_base_sha

    assert _unique_hunk_mapping_status(
        repo,
        old_head_sha,
        new_head_sha,
        recovery_sha,
        ["tracked.txt"],
    ) == "AMBIGUOUS_HUNK_MAPPING"
    assert not _git(
        repo, "status", "--porcelain=v1", "--untracked-files=all"
    ).stdout
    assert recovery_sha in {row.split("\t", 1)[0] for row in _stash_rows(repo)}


def test_unique_hunk_gate_rejects_late_nul_in_wip_blob(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path / "repo")
    tracked = repo / "tracked.txt"
    base_lines = [f"line {index}\n".encode() for index in range(3000)]
    tracked.write_bytes(b"".join(base_lines))
    _git(repo, "commit", "-qam", "large text base")
    _git(repo, "switch", "-qc", "feature")
    (repo / "feature-committed.txt").write_text("feature\n", encoding="utf-8")
    _git(repo, "add", "feature-committed.txt")
    _git(repo, "commit", "-qm", "feature commit before WIP")

    old_head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    wip_lines = base_lines.copy()
    wip_lines[-1] = b"WIP-2999\0tail\n"
    tracked.write_bytes(b"".join(wip_lines))
    _git(repo, "add", "tracked.txt")
    intended_index_tree = _git(repo, "write-tree").stdout.strip()
    _git(repo, "stash", "push", "-m", "late-nul-probe")
    recovery_sha = _git(repo, "rev-parse", "stash@{0}").stdout.strip()
    _assert_stash_captured_index(
        repo, recovery_sha, old_head_sha, intended_index_tree
    )

    _git(repo, "switch", "main")
    base_lines[0] = b"new base line 0\n"
    tracked.write_bytes(b"".join(base_lines))
    _git(repo, "commit", "-qam", "advance distant base line")
    new_base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "switch", "feature")
    _git(repo, "rebase", "main")
    new_head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    assert new_head_sha != new_base_sha

    assert _unique_hunk_mapping_status(
        repo,
        old_head_sha,
        new_head_sha,
        recovery_sha,
        ["tracked.txt"],
    ) == "AMBIGUOUS_HUNK_MAPPING"
    assert not _git(
        repo, "status", "--porcelain=v1", "--untracked-files=all"
    ).stdout
    assert recovery_sha in {row.split("\t", 1)[0] for row in _stash_rows(repo)}


@pytest.mark.parametrize("boundary", ("prepend", "append"))
@pytest.mark.parametrize("mixed_replacement", (False, True))
def test_unique_hunk_gate_blocks_concurrent_boundary_insertions(
    tmp_path: Path,
    boundary: str,
    mixed_replacement: bool,
) -> None:
    repo = _init_repo(tmp_path / "repo")
    tracked = repo / "tracked.txt"
    base_lines = [f"unique {index}\n" for index in range(10)]
    tracked.write_text("".join(base_lines), encoding="utf-8")
    _git(repo, "commit", "-qam", "boundary base")
    _git(repo, "switch", "-qc", "feature")
    (repo / "feature-committed.txt").write_text("feature\n", encoding="utf-8")
    _git(repo, "add", "feature-committed.txt")
    _git(repo, "commit", "-qm", "feature commit before WIP")

    old_head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    wip_base_lines = base_lines.copy()
    if mixed_replacement:
        replacement_index = -1 if boundary == "prepend" else 0
        wip_base_lines[replacement_index] = "WIP replacement\n"
    wip_lines = (
        ["WIP\n", *wip_base_lines]
        if boundary == "prepend"
        else [*wip_base_lines, "WIP\n"]
    )
    tracked.write_text("".join(wip_lines), encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    intended_index_tree = _git(repo, "write-tree").stdout.strip()
    _git(repo, "stash", "push", "-m", f"{boundary}-probe")
    recovery_sha = _git(repo, "rev-parse", "stash@{0}").stdout.strip()
    _assert_stash_captured_index(
        repo, recovery_sha, old_head_sha, intended_index_tree
    )

    _git(repo, "switch", "main")
    main_lines = (
        ["BASE\n", *base_lines]
        if boundary == "prepend"
        else [*base_lines, "BASE\n"]
    )
    tracked.write_text("".join(main_lines), encoding="utf-8")
    _git(repo, "commit", "-qam", f"concurrent {boundary}")
    new_base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "switch", "feature")
    _git(repo, "rebase", "main")
    new_head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    assert new_head_sha != new_base_sha

    assert _unique_hunk_mapping_status(
        repo,
        old_head_sha,
        new_head_sha,
        recovery_sha,
        ["tracked.txt"],
    ) == "AMBIGUOUS_HUNK_MAPPING"
    assert not _git(
        repo, "status", "--porcelain=v1", "--untracked-files=all"
    ).stdout
    assert recovery_sha in {row.split("\t", 1)[0] for row in _stash_rows(repo)}


def test_unique_hunk_gate_rejects_directory_pathspec(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path / "repo")
    nested = repo / "dir" / "nested.txt"
    nested.parent.mkdir()
    nested.write_text("base\n", encoding="utf-8")
    _git(repo, "add", "dir/nested.txt")
    _git(repo, "commit", "-qm", "directory base")
    _git(repo, "switch", "-qc", "feature")
    (repo / "feature-committed.txt").write_text("feature\n", encoding="utf-8")
    _git(repo, "add", "feature-committed.txt")
    _git(repo, "commit", "-qm", "feature commit before WIP")

    old_head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    nested.write_text("feature WIP\n", encoding="utf-8")
    _git(repo, "add", "dir/nested.txt")
    intended_index_tree = _git(repo, "write-tree").stdout.strip()
    _git(repo, "stash", "push", "-m", "directory-pathspec-probe")
    recovery_sha = _git(repo, "rev-parse", "stash@{0}").stdout.strip()
    _assert_stash_captured_index(
        repo, recovery_sha, old_head_sha, intended_index_tree
    )

    _git(repo, "switch", "main")
    nested.write_text("new base\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "advance descendant")
    new_base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "switch", "feature")
    _git(repo, "rebase", "main")
    new_head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    assert new_head_sha != new_base_sha

    assert _unique_hunk_mapping_status(
        repo,
        old_head_sha,
        new_head_sha,
        recovery_sha,
        ["dir/"],
    ) == "AMBIGUOUS_HUNK_MAPPING"
    assert not _git(
        repo, "status", "--porcelain=v1", "--untracked-files=all"
    ).stdout
    assert recovery_sha in {row.split("\t", 1)[0] for row in _stash_rows(repo)}


def test_tree_match_helper_does_not_turn_git_error_into_mismatch(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path / "repo")
    actual_tree = _git(repo, "write-tree").stdout.strip()

    with pytest.raises(AssertionError):
        _trees_match_paths(
            repo,
            "not-a-tree",
            actual_tree,
            ["tracked.txt"],
        )


def test_registry_and_evidence_cover_origin_main_drift() -> None:
    metadata = yaml.safe_load((SKILL_DIR / "skill.yaml").read_text(encoding="utf-8"))
    exceptions = yaml.safe_load(
        (SKILL_DIR / "known-exceptions.yaml").read_text(encoding="utf-8")
    )
    reference = RECOVERY.read_text(encoding="utf-8")
    example = (SKILL_DIR / "examples" / "good-04.md").read_text(encoding="utf-8")
    normalized_reference = " ".join(reference.split())
    normalized_example = " ".join(example.split())

    trigger = (
        "пока шли тесты, main продвинулся; перед commit ещё раз сверь базу "
        "и не потеряй WIP"
    )
    assert trigger in metadata["natural_triggers"]
    assert "examples/good-04.md" in metadata["example_files"]
    assert metadata["last_reviewed"] == "2026-08-24"

    matching = [
        item
        for item in exceptions["exceptions"]
        if item["source_example"] == "examples/good-04.md"
    ]
    assert len(matching) == 1
    assert "origin/main продвинулся" in matching[0]["symptom"]
    assert "object SHA" in matching[0]["do_next_time"]
    assert "через GIT_INDEX_FILE" in matching[0]["do_next_time"]
    assert "expected/actual tree" in matching[0]["do_next_time"]
    assert "UNIQUE_HUNK_MAPPING_PASS" in matching[0]["do_next_time"]
    assert "неоднозначных одинаковых строках" in matching[0]["do_next_time"]
    assert "same-path hunks" in matching[0]["do_next_time"]
    assert "exit status" in matching[0]["do_next_time"]
    assert "не полагаясь на статус последней команды" in matching[0]["do_next_time"]
    assert "нормализованный manifest" in matching[0]["do_next_time"]
    assert "удалить только его" in matching[0]["do_next_time"]
    assert "post-push base/head readback" in matching[0]["do_next_time"]

    for invariant in (
        "это mixed WIP",
        "останавливается до `stash` и `rebase`",
        "INTENDED_PATH_SCOPE_PASS",
        'test "${hunk_scope_state:-UNPROVEN}" = INTENDED_HUNKS_ONLY',
        'print("PLUGIN_CHANGE")',
        "# STABLE_SCOPE_GATE_BEGIN",
        "STABLE_SCOPE_PASS",
        'if stable != intended - allowed_derived:',
        'if ! initial_unmerged=$(git -C "$repo" ls-files -u); then',
        "intended_index_tree",
        'test "$intended_index_tree" = "$tested_tree"',
        "manifest_payload_fingerprint",
        "if ! manifest_payload_fingerprint=$(",
        "comm -13",
        '"${recovery_stash_sha}^2^1"',
        '"${recovery_stash_sha}^2^{tree}"',
        'if ! git -C "$repo" rebase origin/main; then',
        'if ! git -C "$repo" stash apply "$recovery_stash_sha"; then',
        "GIT_INDEX_FILE",
        "git --literal-pathspecs -C \"$repo\" diff",
        "--binary --full-index --unified=8 --no-renames",
        "apply.ignoreWhitespace=false",
        "--cached -C8 --whitespace=nowarn --quiet -",
        "expected_tree",
        "actual_tree",
        'if ((${#stable_paths[@]} == 0)); then',
        "expected_tree=NOT_REQUIRED",
        "APPLIED_SCOPE_PASS",
        "UNIQUE_HUNK_MAPPING_PASS",
        "AMBIGUOUS_HUNK_MAPPING",
        "verifier_reference_path=",
        '"${recovery_stash_sha}^2:${verifier_reference_path}"',
        'cat-file blob "$verifier_blob_sha"',
        'test "$verifier_marker_counts" = 1:1',
        "/^# UNIQUE_HUNK_VERIFIER_BEGIN$/,/^# UNIQUE_HUNK_VERIFIER_END$/p",
        'printf \'%s\\n\' "$verifier_source" | python3 -',
        '"$repo" "$old_head_sha" "$new_head_sha" "$recovery_stash_sha"',
        '"${stable_paths[@]}"',
        "unique_hunk_mapping=AMBIGUOUS_HUNK_MAPPING",
        'test "$unique_hunk_mapping" = UNIQUE_HUNK_MAPPING_PASS',
        'if ! test "$pre_apply_head_sha" = "$new_head_sha"; then',
        "if ! expected_index_dir=$(mktemp -d); then",
        'expected_index_path="${expected_index_dir:?}/index"',
        'test ! -e "$expected_index_path"',
        "recovered_manifest_payload_fingerprint",
        "if ! recovered_manifest_payload_fingerprint=$(",
        "SEMVER_RECALC_PASS",
        "STAGED_SCOPE_PASS",
        "пересчитывает manifest относительно именно новой базы",
        "verified_base_sha=\"$current_base_sha\"",
        "ls-files -u",
        "verified_head_sha",
        'test "${stash_reflog_exclusive_state:-UNPROVEN}" =',
        "drop_candidate_sha=$(git -C \"$repo\" rev-parse \"$stash_ref\")",
        "stash drop \"$stash_ref\"",
        'if ! git -C "$repo" stash drop "$stash_ref"; then',
        'if ! cmp -s "$stash_before_path" "$stash_after_path"; then',
        "HEAD:refs/heads/$branch",
        'ls-remote --exit-code --heads origin "refs/heads/$branch"',
        "--force-with-lease=refs/heads/$branch:$expected_remote_sha",
        'if ! git -C "$repo" push origin "HEAD:refs/heads/$branch"',
        "post_push_base_sha",
        'if ! git -C "$repo" fetch origin --prune; then',
        'if ! post_push_base_sha=$(git -C "$repo" rev-parse origin/main); then',
        "if ! post_push_head_sha=$(",
        "if ! post_push_head_count=$(",
        'if ! test "$post_push_head_count" = 1; then',
        'if ! test "$post_push_head_sha" = "$verified_head_sha"; then',
        'if ! test "$post_push_base_sha" = "$verified_base_sha"; then',
        "test \"$post_push_head_sha\" = \"$verified_head_sha\"",
    ):
        assert invariant in normalized_example

    assert "normalize_wip_diff" not in example
    assert "logical_wip_fingerprint" not in example
    assert 'rev-parse "refs/remotes/origin/$branch"' not in normalized_reference
    assert 'rev-parse "refs/remotes/origin/$branch"' not in normalized_example
    assert normalized_reference.count(
        'ls-remote --exit-code --heads origin "refs/heads/$branch"'
    ) == 2
    assert normalized_example.count(
        'ls-remote --exit-code --heads origin "refs/heads/$branch"'
    ) == 1
    unique_mapping_at = example.index("UNIQUE_HUNK_MAPPING_PASS")
    stash_apply_at = example.index(
        'git -C "$repo" stash apply "$recovery_stash_sha"', unique_mapping_at
    )
    assert unique_mapping_at < stash_apply_at

    repeated_test_at = example.rindex("python -m pytest")
    post_test_fetch_at = example.index(
        'git -C "$repo" fetch origin --prune', repeated_test_at
    )
    verified_base_at = example.index(
        'verified_base_sha="$current_base_sha"', post_test_fetch_at
    )
    commit_at = example.index('git -C "$repo" commit', verified_base_at)
    assert repeated_test_at < post_test_fetch_at < verified_base_at < commit_at

    push_at = example.index('git -C "$repo" push', commit_at)
    post_push_fetch_at = example.index(
        'git -C "$repo" fetch origin --prune', push_at
    )
    head_readback_at = example.index(
        'git -C "$repo" ls-remote --heads origin', post_push_fetch_at
    )
    assert push_at < post_push_fetch_at < head_readback_at


def test_noop_stash_does_not_claim_preexisting_stash(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo")
    (repo / "tracked.txt").write_text("old work\n", encoding="utf-8")
    _git(repo, "stash", "push", "-m", "existing-work", "--", "tracked.txt")
    before = _stash_rows(repo)

    result = _git(
        repo,
        "stash",
        "push",
        "--include-untracked",
        "-m",
        "codex-recovery:main:base:head",
    )
    after = _stash_rows(repo)

    assert result.returncode == 0
    assert after == before
    assert len(after) == 1
    assert "existing-work" in after[0]
    assert "codex-recovery" not in after[0]


def test_mixed_wip_blocks_before_stash_and_preserves_state(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo")
    _git(repo, "switch", "-qc", "feature")
    (repo / "tracked.txt").write_text("older stash\n", encoding="utf-8")
    _git(repo, "stash", "push", "-m", "preexisting", "--", "tracked.txt")
    (repo / "tracked.txt").write_text("intended\n", encoding="utf-8")
    (repo / "foreign.txt").write_text("unrelated\n", encoding="utf-8")

    stashes_before = _stash_rows(repo)
    status_before = _git(
        repo, "status", "--porcelain=v1", "--untracked-files=all"
    ).stdout
    head_before = _git(repo, "rev-parse", "HEAD").stdout.strip()
    dirty_paths = {line[3:] for line in status_before.splitlines()}
    intended_paths = {"tracked.txt"}

    assert dirty_paths != intended_paths
    assert "foreign.txt" in dirty_paths
    assert _stash_rows(repo) == stashes_before
    assert (
        _git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout
        == status_before
    )
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == head_before


def test_same_path_mixed_hunks_are_not_proven_by_path_equality(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path / "repo")
    original = [f"line {index}\n" for index in range(1, 31)]
    (repo / "tracked.txt").write_text("".join(original), encoding="utf-8")
    _git(repo, "commit", "-qam", "long fixture")

    mixed = original.copy()
    mixed[1] = "intended hunk\n"
    mixed[-2] = "foreign hunk\n"
    (repo / "tracked.txt").write_text("".join(mixed), encoding="utf-8")

    status_before = _git(
        repo, "status", "--porcelain=v1", "--untracked-files=all"
    ).stdout
    dirty_paths = {line[3:] for line in status_before.splitlines()}
    assert dirty_paths == {"tracked.txt"}
    diff = _git(repo, "diff", "--unified=0", "--", "tracked.txt").stdout
    assert "intended hunk" in diff
    assert "foreign hunk" in diff
    assert "Неразделимые same-path изменения тоже считаются mixed WIP" in " ".join(
        RECOVERY.read_text(encoding="utf-8").split()
    )
    assert not _stash_rows(repo)
    assert (
        _git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout
        == status_before
    )


def test_precommit_gate_rejects_tree_worktree_untracked_and_unmerged(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path / "scope")
    (repo / "tracked.txt").write_text("approved\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    tested_tree = _git(repo, "write-tree").stdout.strip()
    assert _precommit_gate_is_clean(repo, tested_tree)

    (repo / "tracked.txt").write_text("unstaged drift\n", encoding="utf-8")
    assert not _precommit_gate_is_clean(repo, tested_tree)
    _git(repo, "add", "tracked.txt")
    assert not _precommit_gate_is_clean(repo, tested_tree)

    untracked_repo = _init_repo(tmp_path / "untracked")
    untracked_tree = _git(untracked_repo, "write-tree").stdout.strip()
    (untracked_repo / "new.txt").write_text("unknown\n", encoding="utf-8")
    assert not _precommit_gate_is_clean(untracked_repo, untracked_tree)

    conflict_repo = _init_repo(tmp_path / "conflict")
    _git(conflict_repo, "switch", "-qc", "side")
    (conflict_repo / "tracked.txt").write_text("side\n", encoding="utf-8")
    _git(conflict_repo, "commit", "-qam", "side")
    _git(conflict_repo, "switch", "main")
    (conflict_repo / "tracked.txt").write_text("main\n", encoding="utf-8")
    _git(conflict_repo, "commit", "-qam", "main")
    merge = _git(conflict_repo, "merge", "side", check=False)
    assert merge.returncode != 0
    assert _git(conflict_repo, "ls-files", "-u").stdout
    assert not _precommit_gate_is_clean(conflict_repo, "not-a-tree")


def test_stash_base_advance_apply_delta_compare_commit_roundtrip(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path / "repo")
    (repo / "delete.txt").write_text("remove me\n", encoding="utf-8")
    _git(repo, "add", "delete.txt")
    _git(repo, "commit", "-qm", "add deletion fixture")
    (repo / "tracked.txt").write_text("preexisting stash\n", encoding="utf-8")
    _git(repo, "stash", "push", "-m", "preexisting", "--", "tracked.txt")
    preexisting_shas = {row.split("\t", 1)[0] for row in _stash_rows(repo)}
    _git(repo, "switch", "-qc", "feature")

    paths = ["tracked.txt", "delete.txt", "new.bin"]
    old_head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "tracked.txt").write_text("intended change\n", encoding="utf-8")
    (repo / "tracked.txt").chmod(0o755)
    (repo / "delete.txt").unlink()
    (repo / "new.bin").write_bytes(b"\x00\xffnew binary\n")
    _git(repo, "add", "-A")
    _git(repo, "update-index", "--chmod=+x", "tracked.txt")
    intended_index_tree = _git(repo, "write-tree").stdout.strip()
    with pytest.raises(AssertionError):
        _assert_stash_captured_index(
            repo,
            next(iter(preexisting_shas)),
            old_head_sha,
            intended_index_tree,
        )

    before_rows = _stash_rows(repo)
    before_shas = {row.split("\t", 1)[0] for row in before_rows}
    _git(
        repo,
        "stash",
        "push",
        "--include-untracked",
        "-m",
        "codex-recovery:feature:base:head",
    )
    created_rows = [
        row
        for row in _stash_rows(repo)
        if row.split("\t", 1)[0] not in before_shas
    ]
    assert len(created_rows) == 1
    recovery_sha = created_rows[0].split("\t", 1)[0]
    _assert_stash_captured_index(
        repo, recovery_sha, old_head_sha, intended_index_tree
    )
    assert not _git(
        repo, "status", "--porcelain=v1", "--untracked-files=all"
    ).stdout

    _git(repo, "switch", "main")
    (repo / "base-only.txt").write_text("advanced base\n", encoding="utf-8")
    _git(repo, "add", "base-only.txt")
    _git(repo, "commit", "-qm", "advance base outside intended scope")
    new_base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "switch", "feature")
    _git(repo, "rebase", "main")
    new_head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "stash", "apply", recovery_sha)
    _git(repo, "add", "-A")

    expected_tree = _expected_tree_from_stash(
        repo,
        old_head_sha,
        recovery_sha,
        new_head_sha,
        paths,
        tmp_path / "expected.index",
    )
    actual_tree = _git(repo, "write-tree").stdout.strip()
    assert _trees_match_paths(repo, expected_tree, actual_tree, paths)
    assert _git(repo, "ls-tree", expected_tree, "--", "tracked.txt").stdout.startswith(
        "100755 blob "
    )
    assert not _git(repo, "ls-tree", expected_tree, "--", "delete.txt").stdout
    assert _git(repo, "ls-tree", expected_tree, "--", "new.bin").stdout.startswith(
        "100644 blob "
    )
    assert not (repo / "delete.txt").exists()
    assert (repo / "new.bin").read_bytes() == b"\x00\xffnew binary\n"
    tested_tree = _git(repo, "write-tree").stdout.strip()
    _git(repo, "commit", "-qm", "commit recovered exact delta")
    verified_head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    assert _git(repo, "merge-base", "--is-ancestor", new_base_sha, "HEAD").returncode == 0
    assert (
        _git(repo, "rev-parse", f"{verified_head_sha}^{{tree}}").stdout.strip()
        == tested_tree
    )
    assert not _git(
        repo, "status", "--porcelain=v1", "--untracked-files=all"
    ).stdout

    matching_rows = [
        row
        for row in _stash_rows(repo)
        if row.split("\t", 2)[0] == recovery_sha
        and row.split("\t", 2)[2]
        == "On feature: codex-recovery:feature:base:head"
    ]
    assert len(matching_rows) == 1
    recovery_ref = matching_rows[0].split("\t", 2)[1]
    assert _git(repo, "rev-parse", recovery_ref).stdout.strip() == recovery_sha
    _git(repo, "stash", "drop", recovery_ref)

    remaining_shas = {row.split("\t", 1)[0] for row in _stash_rows(repo)}
    assert recovery_sha not in remaining_shas
    assert remaining_shas == preexisting_shas


@pytest.mark.parametrize(
    (
        "initial_version",
        "intended_version",
        "drifted_version",
        "bump_kind",
        "expected_version",
    ),
    (
        ("0.7.12", "0.7.13", "0.7.13", "patch", "0.7.14"),
        ("0.7.12", "0.8.0", "0.8.0", "minor", "0.9.0"),
        ("0.7.12", "1.0.0", "1.0.0", "major", "2.0.0"),
    ),
)
def test_manifest_semver_bump_kind_is_preserved_without_losing_stable_wip(
    tmp_path: Path,
    initial_version: str,
    intended_version: str,
    drifted_version: str,
    bump_kind: str,
    expected_version: str,
) -> None:
    repo = _init_repo(tmp_path / "repo")
    manifest = repo / "plugins" / "team-skills" / ".codex-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "name": "team-skills",
                "version": initial_version,
                "channel": "stable",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _git(repo, "add", str(manifest.relative_to(repo)))
    _git(repo, "commit", "-qm", "add plugin manifest")
    _git(repo, "switch", "-qc", "feature")

    old_head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "tracked.txt").write_text("feature work\n", encoding="utf-8")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["version"] = intended_version
    manifest.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _git(repo, "add", "-A")
    intended_index_tree = _git(repo, "write-tree").stdout.strip()
    manifest_before = _manifest_payload_fingerprint(manifest)
    assert _semver_bump_kind(initial_version, intended_version) == bump_kind

    before_shas = {row.split("\t", 1)[0] for row in _stash_rows(repo)}
    _git(
        repo,
        "stash",
        "push",
        "--include-untracked",
        "-m",
        "codex-recovery:feature:old-base:old-head",
    )
    recovery_rows = [
        row
        for row in _stash_rows(repo)
        if row.split("\t", 1)[0] not in before_shas
    ]
    assert len(recovery_rows) == 1
    recovery_sha = recovery_rows[0].split("\t", 1)[0]
    _assert_stash_captured_index(
        repo, recovery_sha, old_head_sha, intended_index_tree
    )

    _git(repo, "switch", "main")
    base_payload = json.loads(manifest.read_text(encoding="utf-8"))
    base_payload["version"] = drifted_version
    manifest.write_text(
        json.dumps(base_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _git(repo, "commit", "-qam", "advance base plugin version")
    new_base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    _git(repo, "switch", "feature")
    _git(repo, "rebase", "main")
    new_head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    apply_result = _git(repo, "stash", "apply", recovery_sha, check=False)
    assert apply_result.returncode == 0, apply_result.stderr

    intermediate_status = _git(
        repo, "status", "--porcelain=v1", "--untracked-files=all"
    ).stdout
    intermediate_paths = {line[3:] for line in intermediate_status.splitlines()}
    assert intermediate_paths == {"tracked.txt"}
    assert _manifest_payload_fingerprint(manifest) == manifest_before
    assert json.loads(manifest.read_text(encoding="utf-8"))["version"] == drifted_version

    recovered_payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert _next_semver(drifted_version, bump_kind) == expected_version
    recovered_payload["version"] = expected_version
    manifest.write_text(
        json.dumps(recovered_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _git(repo, "add", "-A")

    expected_tree = _expected_tree_from_stash(
        repo,
        old_head_sha,
        recovery_sha,
        new_head_sha,
        ["tracked.txt"],
        tmp_path / "expected.index",
    )
    actual_tree = _git(repo, "write-tree").stdout.strip()
    assert _trees_match_paths(repo, expected_tree, actual_tree, ["tracked.txt"])
    assert _manifest_payload_fingerprint(manifest) == manifest_before
    assert json.loads(manifest.read_text(encoding="utf-8"))["version"] == expected_version
    staged_paths = set(
        _git(repo, "diff", "--cached", "--name-only").stdout.splitlines()
    )
    assert staged_paths == {
        "tracked.txt",
        "plugins/team-skills/.codex-plugin/plugin.json",
    }
    assert _git(repo, "merge-base", "--is-ancestor", new_base_sha, "HEAD").returncode == 0


def test_delta_mismatch_blocks_commit_and_preserves_recovery_stash(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path / "repo")
    initial_lines = [f"line {index}\n" for index in range(1, 25)]
    (repo / "tracked.txt").write_text("".join(initial_lines), encoding="utf-8")
    _git(repo, "commit", "-qam", "long base")
    _git(repo, "switch", "-qc", "feature")

    old_head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    feature_lines = initial_lines.copy()
    feature_lines[-1] = "feature tail\n"
    (repo / "tracked.txt").write_text("".join(feature_lines), encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    intended_index_tree = _git(repo, "write-tree").stdout.strip()
    before_shas = {row.split("\t", 1)[0] for row in _stash_rows(repo)}
    _git(
        repo,
        "stash",
        "push",
        "--include-untracked",
        "-m",
        "codex-recovery:feature:base:head",
    )
    recovery_rows = [
        row
        for row in _stash_rows(repo)
        if row.split("\t", 1)[0] not in before_shas
    ]
    assert len(recovery_rows) == 1
    recovery_sha = recovery_rows[0].split("\t", 1)[0]
    _assert_stash_captured_index(
        repo, recovery_sha, old_head_sha, intended_index_tree
    )

    _git(repo, "switch", "main")
    base_lines = initial_lines.copy()
    base_lines[0] = "new base head\n"
    (repo / "tracked.txt").write_text("".join(base_lines), encoding="utf-8")
    _git(repo, "commit", "-qam", "advance base inside intended path")
    new_base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "switch", "feature")
    _git(repo, "rebase", "main")
    new_head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "stash", "apply", recovery_sha)
    _git(repo, "add", "-A")

    expected_tree = _expected_tree_from_stash(
        repo,
        old_head_sha,
        recovery_sha,
        new_head_sha,
        ["tracked.txt"],
        tmp_path / "expected.index",
    )
    recovered_tree = _git(repo, "write-tree").stdout.strip()
    assert _trees_match_paths(
        repo, expected_tree, recovered_tree, ["tracked.txt"]
    )

    tampered_lines = (repo / "tracked.txt").read_text(encoding="utf-8").splitlines(
        keepends=True
    )
    tampered_lines[-1] = "tampered tail\n"
    (repo / "tracked.txt").write_text("".join(tampered_lines), encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    mismatched_tree = _git(repo, "write-tree").stdout.strip()
    assert not _trees_match_paths(
        repo, expected_tree, mismatched_tree, ["tracked.txt"]
    )
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == new_head_sha
    assert _git(
        repo, "status", "--porcelain=v1", "--untracked-files=all"
    ).stdout
    assert not _git(repo, "ls-files", "-u").stdout
    assert recovery_sha in {row.split("\t", 1)[0] for row in _stash_rows(repo)}


def test_explicit_force_with_lease_rejects_remote_race(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "-q")

    publisher = _init_repo(tmp_path / "publisher")
    _git(publisher, "remote", "add", "origin", str(remote))
    _git(publisher, "push", "-u", "origin", "main")
    _git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
    _git(publisher, "switch", "-qc", "feature")
    (publisher / "tracked.txt").write_text("publisher v1\n", encoding="utf-8")
    _git(publisher, "commit", "-qam", "publisher v1")
    _git(publisher, "push", "-u", "origin", "feature")
    expected_remote_sha = _git(
        publisher, "rev-parse", "refs/remotes/origin/feature"
    ).stdout.strip()

    competitor = tmp_path / "competitor"
    clone = subprocess.run(
        ["git", "clone", "-q", str(remote), str(competitor)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert clone.returncode == 0, clone.stderr
    _git(competitor, "config", "user.name", "Other User")
    _git(competitor, "config", "user.email", "other@example.invalid")
    _git(competitor, "config", "commit.gpgsign", "false")
    _git(competitor, "switch", "-c", "feature", "--track", "origin/feature")
    (competitor / "tracked.txt").write_text("competitor v2\n", encoding="utf-8")
    _git(competitor, "commit", "-qam", "competitor v2")
    _git(competitor, "push", "origin", "feature")
    competitor_sha = _git(competitor, "rev-parse", "HEAD").stdout.strip()

    (publisher / "tracked.txt").write_text("rewritten v1\n", encoding="utf-8")
    _git(publisher, "commit", "-qam", "rewrite locally")
    lease = f"--force-with-lease=refs/heads/feature:{expected_remote_sha}"
    push = _git(
        publisher,
        "push",
        "origin",
        "HEAD:refs/heads/feature",
        lease,
        check=False,
    )

    assert push.returncode != 0
    assert _git(remote, "rev-parse", "refs/heads/feature").stdout.strip() == competitor_sha


def test_direct_remote_lease_works_with_main_only_fetch(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "-q")

    publisher = _init_repo(tmp_path / "publisher")
    _git(publisher, "remote", "add", "origin", str(remote))
    _git(publisher, "push", "-u", "origin", "main")
    _git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
    _git(publisher, "switch", "-qc", "feature")
    (publisher / "tracked.txt").write_text("feature\n", encoding="utf-8")
    _git(publisher, "commit", "-qam", "feature")
    _git(publisher, "push", "origin", "feature")
    remote_feature_sha = _git(
        remote, "rev-parse", "refs/heads/feature"
    ).stdout.strip()

    observer = tmp_path / "observer"
    clone = subprocess.run(
        ["git", "clone", "-q", str(remote), str(observer)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert clone.returncode == 0, clone.stderr
    _git(observer, "config", "--unset-all", "remote.origin.fetch")
    _git(
        observer,
        "config",
        "--add",
        "remote.origin.fetch",
        "+refs/heads/main:refs/remotes/origin/main",
    )
    _git(observer, "update-ref", "-d", "refs/remotes/origin/feature")
    _git(observer, "fetch", "origin", "--prune")
    assert _git(
        observer, "rev-parse", "refs/remotes/origin/feature", check=False
    ).returncode != 0

    direct = _git(
        observer,
        "ls-remote",
        "--exit-code",
        "--heads",
        "origin",
        "refs/heads/feature",
    )
    assert direct.stdout.splitlines() == [
        f"{remote_feature_sha}\trefs/heads/feature"
    ]
