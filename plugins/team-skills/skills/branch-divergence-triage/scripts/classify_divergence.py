#!/usr/bin/env python3
"""
Классификация файлов отставшей ветки относительно базы и вердикт о стратегии переноса.

Отвечает на один вопрос: что в ветке своё, а что уже есть в базе. Ничего не меняет —
только читает объекты Git.

Классы файлов:
  IDENTICAL   — совпали и содержимое, и режим записи дерева; переносить нечего;
  STALE_ONLY  — всё, что ветка добавила и удалила, база уже сделала сама;
  UNIQUE      — ветка несёт изменение, которого в базе нет, а база файл не трогала;
  CONFLICTING — файл меняли обе стороны, либо изменение нельзя развести автоматически.

Вердикты:
  REBASE_SAFE      — ветка только впереди базы;
  SUPERSEDED       — уникального нет, ветка закрывается;
  MANUAL_ASSEMBLY  — уникальное лежит в файлах, которых база не трогала;
  NEEDS_REVIEW     — есть файлы класса CONFLICTING, решает человек.

Коды возврата:
  0 — классификация построена, вердикт не требует решения человека;
  1 — ошибка входа: нет repo, не разрешается ref, неверные аргументы;
  2 — упал git или самотест признал детектор мёртвым;
  3 — нужно решение человека: вердикт NEEDS_REVIEW либо статус BLOCKED_DIRTY_TREE.

Предел метода: сравнение идёт по составу строк с учётом кратности. Чистая перестановка
строк без изменения состава распознаётся как изменение, но какое именно — скрипт не знает
и отдаёт такой файл человеку.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Sequence

# SHA-1 и SHA-256: репозиторий может быть создан с --object-format=sha256.
GIT_OID_RE = re.compile(r"^[0-9a-f]{40}$|^[0-9a-f]{64}$")

CLASS_IDENTICAL = "IDENTICAL"
CLASS_STALE_ONLY = "STALE_ONLY"
CLASS_UNIQUE = "UNIQUE"
CLASS_CONFLICTING = "CONFLICTING"
FILE_CLASSES = (CLASS_IDENTICAL, CLASS_STALE_ONLY, CLASS_UNIQUE, CLASS_CONFLICTING)

VERDICT_REBASE_SAFE = "REBASE_SAFE"
VERDICT_SUPERSEDED = "SUPERSEDED"
VERDICT_MANUAL_ASSEMBLY = "MANUAL_ASSEMBLY"
VERDICT_NEEDS_REVIEW = "NEEDS_REVIEW"

STATUS_CLASSIFIED = "DIVERGENCE_CLASSIFIED"
STATUS_BLOCKED_DIRTY = "BLOCKED_DIRTY_TREE"

EXIT_OK = 0
EXIT_INPUT = 1
EXIT_GIT = 2
EXIT_REVIEW = 3


class GitFailure(Exception):
    """Внешний вызов git не дал пригодного результата."""


# ------------------------------------------------------------------ обёртки git

def run_git_bytes(repo: Path, *args: str) -> bytes:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise GitFailure(f"git {' '.join(args)}: {detail[-1] if detail else 'без сообщения'}")
    return proc.stdout


def run_git_text(repo: Path, *args: str) -> str:
    return run_git_bytes(repo, *args).decode("utf-8", "replace").strip()


def resolve_commit(repo: Path, revision: str) -> str:
    oid = run_git_text(repo, "rev-parse", "--verify", f"{revision}^{{commit}}")
    if not GIT_OID_RE.match(oid):
        raise GitFailure(f"ревизия {revision!r} не разрешается в коммит")
    return oid


def tree_entries(repo: Path, commit: str) -> dict[str, tuple[str, str]]:
    """Путь -> (режим, идентификатор объекта). Режим нужен, чтобы видеть смену прав."""
    raw = run_git_bytes(repo, "ls-tree", "-r", "-z", commit)
    entries: dict[str, tuple[str, str]] = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        head, _, raw_path = record.partition(b"\t")
        try:
            path = raw_path.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise GitFailure("git вернул путь не в UTF-8; состав ветки не доказан") from exc
        parts = head.decode("utf-8", "replace").split()
        if len(parts) < 3:
            continue
        entries[path] = (parts[0], parts[2])
    return entries


def blob_bytes(repo: Path, oid: str) -> bytes:
    return run_git_bytes(repo, "cat-file", "blob", oid)


# ------------------------------------------------------------------ классификация

def line_counter(data: bytes | None) -> Counter | None:
    """Мультимножество строк: кратность важна, иначе повтор строки теряется."""
    if data is None:
        return Counter()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return Counter(text.splitlines())


def covered_by(part: Counter, whole: Counter) -> bool:
    return all(whole[line] >= count for line, count in part.items())


def classify_file(path, merge_base_entry, base_entry, branch_entry, blobs, base_touched):
    """Один файл. Отделено от печати ради тестируемости."""
    if branch_entry is None:
        return {"path": path, "class": CLASS_CONFLICTING,
                "reason": "ветка удалила файл: развести автоматически нельзя"}

    if base_entry is None:
        # База удалила файл, который был в точке слияния, — перенос его воскресит.
        if base_touched:
            return {"path": path, "class": CLASS_CONFLICTING,
                    "reason": "база удалила файл, ветка его меняла"}
        return {"path": path, "class": CLASS_UNIQUE, "reason": "файла нет в базе"}

    if branch_entry == base_entry:
        return {"path": path, "class": CLASS_IDENTICAL,
                "reason": "совпали содержимое и режим"}

    if branch_entry[1] == base_entry[1]:
        return {"path": path,
                "class": CLASS_CONFLICTING if base_touched else CLASS_UNIQUE,
                "reason": f"содержимое то же, режим другой: {base_entry[0]} против {branch_entry[0]}"}

    branch_lines = line_counter(blobs["branch"])
    base_lines = line_counter(blobs["base"])
    merge_base_lines = line_counter(blobs["merge_base"])
    if branch_lines is None or base_lines is None or merge_base_lines is None:
        return {"path": path,
                "class": CLASS_CONFLICTING if base_touched else CLASS_UNIQUE,
                "reason": "двоичный файл или не UTF-8: сравнение строк неприменимо"}

    added_by_branch = branch_lines - merge_base_lines
    removed_by_branch = merge_base_lines - branch_lines
    removed_by_base = merge_base_lines - base_lines

    if not added_by_branch and not removed_by_branch:
        # Состав строк тот же, а содержимое другое: перестановка или изменение
        # пробелов. Множествами это не разбирается — отдаём человеку.
        return {"path": path,
                "class": CLASS_CONFLICTING if base_touched else CLASS_UNIQUE,
                "reason": "состав строк тот же, порядок или пробелы другие"}

    added_covered = covered_by(added_by_branch, base_lines)
    removed_covered = covered_by(removed_by_branch, removed_by_base)
    if added_covered and removed_covered:
        return {"path": path, "class": CLASS_STALE_ONLY,
                "reason": (f"добавлено {sum(added_by_branch.values())}, удалено "
                           f"{sum(removed_by_branch.values())} строк — база сделала то же")}

    unique_added = sum((added_by_branch - base_lines).values())
    unique_removed = sum((removed_by_branch - removed_by_base).values())
    return {"path": path,
            "class": CLASS_CONFLICTING if base_touched else CLASS_UNIQUE,
            "reason": f"своих строк: добавлено {unique_added}, удалено {unique_removed}"}


def decide_verdict(files, only_ahead):
    if only_ahead:
        return VERDICT_REBASE_SAFE
    classes = {entry["class"] for entry in files}
    if CLASS_CONFLICTING in classes:
        return VERDICT_NEEDS_REVIEW
    if CLASS_UNIQUE in classes:
        return VERDICT_MANUAL_ASSEMBLY
    return VERDICT_SUPERSEDED


def analyze(repo: Path, branch_ref: str, base_ref: str, allow_dirty: bool = False) -> dict:
    branch = resolve_commit(repo, branch_ref)
    base = resolve_commit(repo, base_ref)
    merge_base = run_git_text(repo, "merge-base", base, branch)
    if not GIT_OID_RE.match(merge_base):
        raise GitFailure("не удалось найти точку слияния ветки и базы")

    dirty = bool(run_git_text(repo, "status", "--porcelain"))
    if dirty and not allow_dirty:
        return {
            "repo": str(repo),
            "branch": {"ref": branch_ref, "commit": branch},
            "base": {"ref": base_ref, "commit": base},
            "merge_base": merge_base,
            "working_tree_dirty": True,
            "files": [],
            "counts": {name: 0 for name in FILE_CLASSES},
            "verdict": None,
            "status": STATUS_BLOCKED_DIRTY,
        }

    branch_tree = tree_entries(repo, branch)
    base_tree = tree_entries(repo, base)
    merge_base_tree = tree_entries(repo, merge_base)

    # Точка слияния, а не вершина базы: иначе чужие коммиты попадут в сравнение.
    branch_paths = {p for p in set(branch_tree) | set(merge_base_tree)
                    if branch_tree.get(p) != merge_base_tree.get(p)}
    base_paths = {p for p in set(base_tree) | set(merge_base_tree)
                  if base_tree.get(p) != merge_base_tree.get(p)}

    files = []
    for path in sorted(branch_paths):
        branch_entry = branch_tree.get(path)
        base_entry = base_tree.get(path)
        merge_base_entry = merge_base_tree.get(path)
        blobs = {
            "branch": blob_bytes(repo, branch_entry[1]) if branch_entry else None,
            "base": blob_bytes(repo, base_entry[1]) if base_entry else None,
            "merge_base": blob_bytes(repo, merge_base_entry[1]) if merge_base_entry else None,
        }
        files.append(
            classify_file(path, merge_base_entry, base_entry, branch_entry, blobs, path in base_paths)
        )

    only_ahead = merge_base == base
    return {
        "repo": str(repo),
        "branch": {"ref": branch_ref, "commit": branch},
        "base": {"ref": base_ref, "commit": base},
        "merge_base": merge_base,
        "only_ahead": only_ahead,
        "working_tree_dirty": dirty,
        "counts": {name: sum(1 for e in files if e["class"] == name) for name in FILE_CLASSES},
        "files": files,
        "verdict": decide_verdict(files, only_ahead),
        "status": STATUS_CLASSIFIED,
    }


# ------------------------------------------------------------------ самотест

# Каждый случай: имя -> (в точке слияния, в базе, в ветке). None — файла нет.
SELFTEST_CASE = {
    "identical.txt": ("общая\n", "общая\nот базы\n", "общая\nот базы\n"),
    "stale.txt": ("общая\n", "общая\nобщая правка\nхвост базы\n", "общая\nобщая правка\n"),
    "unique.txt": (None, None, "только ветка\n"),
    "conflicting.txt": ("общая\n", "общая\nот базы\n", "общая\nот ветки\n"),
    "branch_deletes.txt": ("первая\nвторая\nтретья\n", "первая\nвторая\nтретья\n", "первая\nтретья\n"),
    "base_deleted.txt": ("общая\n", None, "общая\nправка ветки\n"),
    "reordered.txt": ("альфа\nбета\n", "альфа\nбета\n", "бета\nальфа\n"),
}
SELFTEST_EXPECTED = {
    "identical.txt": CLASS_IDENTICAL,
    "stale.txt": CLASS_STALE_ONLY,
    "unique.txt": CLASS_UNIQUE,
    "conflicting.txt": CLASS_CONFLICTING,
    # Ветка только удаляет строку, база файл не трогала: это своя работа, не «нечего переносить».
    "branch_deletes.txt": CLASS_UNIQUE,
    # База удалила файл, ветка его правила: перенос воскресил бы удалённое.
    "base_deleted.txt": CLASS_CONFLICTING,
    # Состав строк тот же, порядок другой: множествами не разбирается.
    "reordered.txt": CLASS_UNIQUE,
    # Ветка сняла бит исполнения: содержимое то же, изменение реальное.
    "mode.sh": CLASS_UNIQUE,
}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=selftest",
         "-c", "user.email=selftest@example.invalid", *args],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
    )


def _write(repo: Path, name: str, content: str | None) -> None:
    target = repo / name
    if content is None:
        target.unlink(missing_ok=True)
    else:
        target.write_text(content, encoding="utf-8")


def selftest() -> list[str]:
    """Синтетический repo с заранее известными случаями. Возвращает список расхождений."""
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        _git(repo, "init", "--initial-branch=base")
        for name, (at_merge_base, _, _) in SELFTEST_CASE.items():
            _write(repo, name, at_merge_base)
        _write(repo, "mode.sh", "#!/bin/sh\necho ok\n")
        (repo / "mode.sh").chmod(0o755)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "точка слияния")

        _git(repo, "switch", "-c", "feature")
        for name, (_, _, in_branch) in SELFTEST_CASE.items():
            _write(repo, name, in_branch)
        # Снимаем бит исполнения на диске: add подхватит режим оттуда,
        # и рабочее дерево останется чистым для обратного переключения.
        (repo / "mode.sh").chmod(0o644)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "работа ветки")

        _git(repo, "switch", "base")
        for name, (_, in_base, _) in SELFTEST_CASE.items():
            _write(repo, name, in_base)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "работа базы")

        result = analyze(repo, "feature", "base", allow_dirty=True)
        got = {entry["path"]: entry["class"] for entry in result["files"]}
        for name, expected in SELFTEST_EXPECTED.items():
            actual = got.get(name, "не классифицирован")
            if actual != expected:
                problems.append(f"{name}: ждали {expected}, получили {actual}")
        if result["verdict"] != VERDICT_NEEDS_REVIEW:
            problems.append(f"вердикт: ждали {VERDICT_NEEDS_REVIEW}, получили {result['verdict']}")
    return problems


# ------------------------------------------------------------------ вывод

VERDICT_HINT = {
    VERDICT_REBASE_SAFE: "ветка только впереди базы: перенос механический",
    VERDICT_SUPERSEDED: "уникального нет, переносить нечего — ветку можно закрывать",
    VERDICT_MANUAL_ASSEMBLY: "собрать ветку заново от свежей базы и перенести только уникальные файлы",
    VERDICT_NEEDS_REVIEW: "есть файлы, которые нельзя развести автоматически: решение за человеком",
}


def render(result: dict) -> str:
    lines = [
        f"ветка: {result['branch']['ref']} ({result['branch']['commit'][:7]})",
        f"база:  {result['base']['ref']} ({result['base']['commit'][:7]})",
        f"точка слияния: {result['merge_base'][:7]}",
        "",
    ]
    if result["status"] == STATUS_BLOCKED_DIRTY:
        lines.append("СТАТУС: BLOCKED_DIRTY_TREE — в рабочем дереве есть незакоммиченные изменения.")
        lines.append("Вердикт по неполному содержимому ветки не выносится.")
        lines.append("Зафиксируйте работу коммитом либо запустите с --allow-dirty, если она к делу не относится.")
        return "\n".join(lines)

    width = max((len(e["path"]) for e in result["files"]), default=10)
    for entry in result["files"]:
        lines.append(f"  {entry['class']:<12} {entry['path']:<{width}}  {entry['reason']}")
    if result["files"]:
        lines.append("")
    counts = result["counts"]
    lines.append("итого: " + ", ".join(f"{name} {counts[name]}" for name in FILE_CLASSES))
    lines.append("")
    lines.append(f"ВЕРДИКТ: {result['verdict']} — {VERDICT_HINT[result['verdict']]}")
    lines.append("")
    lines.append("Классы IDENTICAL и STALE_ONLY переносить не нужно: их содержимое уже в базе.")
    lines.append("Перенос выполняет навык git-pr-lifecycle-safeguard, этот вердикт задаёт его состав.")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Классификация расхождения ветки с базой.")
    parser.add_argument("--repo", help="путь к репозиторию")
    parser.add_argument("--branch", help="разбираемая ветка")
    parser.add_argument("--base", default="origin/main", help="база сравнения (по умолчанию origin/main)")
    parser.add_argument("--allow-dirty", action="store_true",
                        help="разбирать, даже если в рабочем дереве есть незакоммиченные изменения")
    parser.add_argument("--json", action="store_true", help="машинный вывод")
    parser.add_argument("--selftest", action="store_true", help="проверить сам детектор и выйти")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.selftest:
        try:
            problems = selftest()
        except (GitFailure, subprocess.CalledProcessError) as exc:
            print(f"ОШИБКА: самотест не выполнился: {exc}", file=sys.stderr)
            return EXIT_GIT
        if problems:
            print("ДЕТЕКТОР МЁРТВ:", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            return EXIT_GIT
        print(f"самотест пройден: распознано случаев — {len(SELFTEST_EXPECTED)}")
        return EXIT_OK

    if not args.repo or not args.branch:
        print("ОШИБКА: нужны --repo и --branch (или --selftest)", file=sys.stderr)
        return EXIT_INPUT
    repo = Path(args.repo).expanduser()
    if not (repo / ".git").exists() and not (repo.is_dir() and (repo / "HEAD").exists()):
        print(f"ОШИБКА: {repo} не похож на репозиторий git", file=sys.stderr)
        return EXIT_INPUT

    try:
        result = analyze(repo, args.branch, args.base, allow_dirty=args.allow_dirty)
    except GitFailure as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        return EXIT_GIT

    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else render(result))
    if result["status"] == STATUS_BLOCKED_DIRTY or result["verdict"] == VERDICT_NEEDS_REVIEW:
        return EXIT_REVIEW
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
