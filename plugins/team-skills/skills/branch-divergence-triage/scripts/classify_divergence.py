#!/usr/bin/env python3
"""
Классификация файлов отставшей ветки относительно базы и вердикт о стратегии переноса.

Отвечает на один вопрос: что в ветке своё, а что уже есть в базе. Ничего не меняет —
только читает объекты Git.

Классы файлов:
  IDENTICAL   — хэш blob в ветке равен хэшу в базе; переносить нечего;
  STALE_ONLY  — все строки, добавленные веткой над точкой слияния, уже есть в базе;
  UNIQUE      — ветка добавляет строки, которых в базе нет, а база файл не трогала;
  CONFLICTING — и ветка, и база меняли файл, ни одна не является надмножеством.

Вердикты:
  REBASE_SAFE      — ветка только впереди базы;
  SUPERSEDED       — уникального нет, ветка закрывается;
  MANUAL_ASSEMBLY  — уникальное лежит в файлах, которых база не трогала;
  NEEDS_REVIEW     — есть файлы класса CONFLICTING, решает человек.

Коды возврата:
  0 — классификация построена, вердикт не требует решения человека;
  1 — ошибка входа: нет repo, не разрешается ref, неверные аргументы;
  2 — упал git или самотест признал детектор мёртвым;
  3 — вердикт NEEDS_REVIEW: формат чист, но решение принимает человек.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence

GIT_OID_RE = re.compile(r"^[0-9a-f]{40}$")

CLASS_IDENTICAL = "IDENTICAL"
CLASS_STALE_ONLY = "STALE_ONLY"
CLASS_UNIQUE = "UNIQUE"
CLASS_CONFLICTING = "CONFLICTING"
FILE_CLASSES = (CLASS_IDENTICAL, CLASS_STALE_ONLY, CLASS_UNIQUE, CLASS_CONFLICTING)

VERDICT_REBASE_SAFE = "REBASE_SAFE"
VERDICT_SUPERSEDED = "SUPERSEDED"
VERDICT_MANUAL_ASSEMBLY = "MANUAL_ASSEMBLY"
VERDICT_NEEDS_REVIEW = "NEEDS_REVIEW"

EXIT_OK = 0
EXIT_INPUT = 1
EXIT_GIT = 2
EXIT_REVIEW = 3

# Синтетический сценарий самотеста: имя файла -> (в точке слияния, в базе, в ветке).
# None означает, что файла в этой ревизии нет.
SELFTEST_CASE = {
    "identical.txt": ("общая строка\n", "общая строка\nдобавила база\n", "общая строка\nдобавила база\n"),
    "stale.txt": ("общая строка\n", "общая строка\nобщая правка\nхвост базы\n", "общая строка\nобщая правка\n"),
    "unique.txt": ("общая строка\n", None, "общая строка\nтолько ветка\n"),
    "conflicting.txt": ("общая строка\n", "общая строка\nстрока базы\n", "общая строка\nстрока ветки\n"),
}
SELFTEST_EXPECTED = {
    "identical.txt": CLASS_IDENTICAL,
    "stale.txt": CLASS_STALE_ONLY,
    "unique.txt": CLASS_UNIQUE,
    "conflicting.txt": CLASS_CONFLICTING,
}


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
        tail = detail[-1] if detail else "без сообщения"
        raise GitFailure(f"git {' '.join(args)}: {tail}")
    return proc.stdout


def run_git_text(repo: Path, *args: str) -> str:
    return run_git_bytes(repo, *args).decode("utf-8", "replace").strip()


def decode_nul_paths(output: bytes) -> set[str]:
    """Пути от git читаем через -z и разбираем по NUL: имена бывают с пробелами и кириллицей."""
    paths: set[str] = set()
    for raw_path in output.split(b"\0"):
        if not raw_path:
            continue
        try:
            paths.add(raw_path.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise GitFailure("git вернул путь не в UTF-8; состав ветки не доказан") from exc
    return paths


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def resolve_commit(repo: Path, revision: str) -> str:
    oid = run_git_text(repo, "rev-parse", "--verify", f"{revision}^{{commit}}")
    if not GIT_OID_RE.match(oid):
        raise GitFailure(f"ревизия {revision!r} не разрешается в коммит")
    return oid


def blob_bytes(repo: Path, commit: str, path: str) -> bytes | None:
    """Содержимое файла в конкретной ревизии; None, если файла там нет."""
    proc = subprocess.run(
        ["git", "-C", str(repo), "show", f"{commit}:{path}"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc.stdout if proc.returncode == 0 else None


def changed_paths(repo: Path, left: str, right: str) -> set[str]:
    return decode_nul_paths(
        run_git_bytes(repo, "diff", "--name-only", "-z", "--no-renames", left, right, "--")
    )


# ------------------------------------------------------------------ классификация

def line_set(data: bytes | None) -> set[str] | None:
    """Множество строк файла; None, если файла нет или он не текстовый."""
    if data is None:
        return None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return set(text.splitlines())


def classify_file(path, merge_base_blob, base_blob, branch_blob, base_touched):
    """Один файл. Отделено от печати ради тестируемости."""
    if branch_blob is None:
        # Ветка удалила файл: сама по себе арифметика строк этого не решает.
        return {"path": path, "class": CLASS_CONFLICTING, "reason": "ветка удалила файл, база его сохранила"}

    branch_hash = sha256_bytes(branch_blob)
    if base_blob is not None and branch_hash == sha256_bytes(base_blob):
        return {"path": path, "class": CLASS_IDENTICAL, "reason": "хэш blob совпал с базой"}

    if base_blob is None:
        return {"path": path, "class": CLASS_UNIQUE, "reason": "файла нет в базе"}

    branch_lines = line_set(branch_blob)
    base_lines = line_set(base_blob)
    merge_base_lines = line_set(merge_base_blob) or set()
    if branch_lines is None or base_lines is None:
        return {
            "path": path,
            "class": CLASS_CONFLICTING if base_touched else CLASS_UNIQUE,
            "reason": "двоичный файл или не UTF-8: сравнение строк неприменимо",
        }

    added_by_branch = branch_lines - merge_base_lines
    unique = added_by_branch - base_lines
    if not unique:
        return {
            "path": path,
            "class": CLASS_STALE_ONLY,
            "reason": f"ветка добавила {len(added_by_branch)} строк, все уже есть в базе",
        }
    return {
        "path": path,
        "class": CLASS_CONFLICTING if base_touched else CLASS_UNIQUE,
        "reason": f"строк, которых нет в базе: {len(unique)}",
    }


def decide_verdict(files, only_ahead):
    if only_ahead:
        return VERDICT_REBASE_SAFE
    classes = {entry["class"] for entry in files}
    if CLASS_CONFLICTING in classes:
        return VERDICT_NEEDS_REVIEW
    if CLASS_UNIQUE in classes:
        return VERDICT_MANUAL_ASSEMBLY
    return VERDICT_SUPERSEDED


def analyze(repo: Path, branch_ref: str, base_ref: str) -> dict:
    branch = resolve_commit(repo, branch_ref)
    base = resolve_commit(repo, base_ref)
    merge_base = run_git_text(repo, "merge-base", base, branch)
    if not GIT_OID_RE.match(merge_base):
        raise GitFailure("не удалось найти точку слияния ветки и базы")

    # Точка слияния, а не вершина базы: иначе вычитание множеств строк врёт.
    branch_paths = changed_paths(repo, merge_base, branch)
    base_paths = changed_paths(repo, merge_base, base)

    files = []
    for path in sorted(branch_paths):
        files.append(
            classify_file(
                path,
                blob_bytes(repo, merge_base, path),
                blob_bytes(repo, base, path),
                blob_bytes(repo, branch, path),
                path in base_paths,
            )
        )

    only_ahead = merge_base == base
    counts = {name: sum(1 for e in files if e["class"] == name) for name in FILE_CLASSES}
    dirty = bool(run_git_text(repo, "status", "--porcelain"))
    return {
        "repo": str(repo),
        "branch": {"ref": branch_ref, "commit": branch},
        "base": {"ref": base_ref, "commit": base},
        "merge_base": merge_base,
        "only_ahead": only_ahead,
        "working_tree_dirty": dirty,
        "counts": counts,
        "files": files,
        "verdict": decide_verdict(files, only_ahead),
        "status": "DIVERGENCE_CLASSIFIED",
    }


# ------------------------------------------------------------------ самотест

def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=selftest", "-c", "user.email=selftest@example.invalid", *args],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
    )


def _write(repo: Path, name: str, content: str | None) -> None:
    target = repo / name
    if content is None:
        target.unlink(missing_ok=True)
    else:
        target.write_text(content, encoding="utf-8")


def selftest() -> list[str]:
    """Синтетический repo с четырьмя заранее известными случаями. Возвращает список расхождений."""
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        _git(repo, "init", "--initial-branch=base")
        for name, (at_merge_base, _, _) in SELFTEST_CASE.items():
            _write(repo, name, at_merge_base)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "точка слияния")

        _git(repo, "switch", "-c", "feature")
        for name, (_, _, in_branch) in SELFTEST_CASE.items():
            _write(repo, name, in_branch)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "работа ветки")

        _git(repo, "switch", "base")
        for name, (_, in_base, _) in SELFTEST_CASE.items():
            _write(repo, name, in_base)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "работа базы")

        result = analyze(repo, "feature", "base")
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
    VERDICT_NEEDS_REVIEW: "есть файлы, которые меняли обе стороны: решение за человеком",
}


def render(result: dict) -> str:
    lines = [
        f"ветка: {result['branch']['ref']} ({result['branch']['commit'][:7]})",
        f"база:  {result['base']['ref']} ({result['base']['commit'][:7]})",
        f"точка слияния: {result['merge_base'][:7]}",
        "",
    ]
    if result["working_tree_dirty"]:
        lines.append("ВНИМАНИЕ: в рабочем дереве есть незакоммиченные изменения — они в разбор не входят")
        lines.append("")
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
        print("самотест пройден: четыре класса распознаны верно")
        return EXIT_OK

    if not args.repo or not args.branch:
        print("ОШИБКА: нужны --repo и --branch (или --selftest)", file=sys.stderr)
        return EXIT_INPUT
    repo = Path(args.repo).expanduser()
    if not (repo / ".git").exists() and not (repo.is_dir() and (repo / "HEAD").exists()):
        print(f"ОШИБКА: {repo} не похож на репозиторий git", file=sys.stderr)
        return EXIT_INPUT

    try:
        result = analyze(repo, args.branch, args.base)
    except GitFailure as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        return EXIT_GIT

    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else render(result))
    return EXIT_REVIEW if result["verdict"] == VERDICT_NEEDS_REVIEW else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
