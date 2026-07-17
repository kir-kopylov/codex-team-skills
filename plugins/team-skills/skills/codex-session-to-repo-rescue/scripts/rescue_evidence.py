#!/usr/bin/env python3
"""Инвентаризирует Codex-session и проверяет evidence manifest по Git byte sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path, PurePosixPath
from typing import Iterator, Sequence
from urllib.parse import urlsplit, urlunsplit


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_OID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
THREAD_ID_RE = re.compile(r"^[0-9a-fA-F-]{16,64}$")
THREAD_ID_SEARCH_RE = re.compile(
    r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}"
)
TOOL_PATH_LITERAL_RE = re.compile(
    r"\b(?:cwd|workdir)\s*:\s*(?:\"((?:\\.|[^\"\\])*)\"|'((?:\\.|[^'\\])*)')"
)
WINDOWS_ABSOLUTE_PATH_RE = re.compile(r'''[A-Za-z]:\\[^"'\r\n]+''')
POSIX_QUOTED_PATH_RE = re.compile(r'''["'](/[^"'\r\n]+)["']''')
ALLOWED_SOURCES = {"working", "index", "commit", "checkout"}
LOCAL_STATE_ROOTS = {".codex", ".goal-runtime"}
MAX_PATH_HINTS = 128
LOCAL_STATE_FILES = {
    ".codex-global-state.json",
    "session_index.jsonl",
    "target-lock.json",
}
MIB = 1024 * 1024
TARGET_LOCK_KIND = "codex-session-target-lock"
TARGET_LOCK_VERSION = 1
TARGET_TITLE_RECORD_LIMIT = 200


class RescueError(RuntimeError):
    """Ожидаемая ошибка проверки с понятным сообщением для CLI."""


def normalize_title(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def size_mib_rounded(size_bytes: int) -> str:
    value = Decimal(size_bytes) / Decimal(MIB)
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def parse_expected_size_mib(raw_value: str | None) -> Decimal | None:
    if raw_value is None:
        return None
    try:
        value = Decimal(raw_value.replace(",", "."))
        if not value.is_finite():
            raise RescueError("expected_size_mib должен быть конечным числом")
        if value < 0:
            raise RescueError("expected_size_mib не может быть отрицательным")
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise RescueError("expected_size_mib должен быть конечным числом") from exc


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sanitize_remote_url(raw_url: str) -> str:
    """Удалить credentials, query и fragment, сохранив host/path для provenance."""

    value = raw_url.strip()
    if not value:
        return value

    if re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith(("\\\\", "//")):
        return value.split("?", 1)[0].split("#", 1)[0]

    if "://" in value:
        parsed = urlsplit(value)
        hostname = parsed.hostname or ""
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        port = f":{parsed.port}" if parsed.port else ""
        safe_netloc = f"{hostname}{port}"
        return urlunsplit((parsed.scheme, safe_netloc, parsed.path, "", ""))

    scp_match = re.match(r"^(?:[^@/\s]+@)?([^:/\s]+):(.+)$", value)
    if scp_match:
        host, remote_path = scp_match.groups()
        remote_path = remote_path.split("?", 1)[0].split("#", 1)[0]
        return f"ssh://{host}/{remote_path.lstrip('/')}"

    return value.split("?", 1)[0].split("#", 1)[0]


def run_git_bytes(repo: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RescueError(f"Git-команда не выполнена: git {' '.join(arguments)}: {message}")
    return completed.stdout


def run_git_text(repo: Path, *arguments: str) -> str:
    return run_git_bytes(repo, *arguments).decode("utf-8", errors="replace").rstrip("\r\n")


def resolve_commit(repo: Path, revision: str, label: str) -> str:
    """Превратить недоверенную revision в OID до использования в других Git-командах."""

    if not revision or "\0" in revision:
        raise RescueError(f"{label} должен быть непустой Git revision")
    try:
        resolved = run_git_text(
            repo,
            "rev-parse",
            "--verify",
            "--end-of-options",
            f"{revision}^{{commit}}",
        ).strip()
    except RescueError as exc:
        raise RescueError(f"{label} не разрешается в commit") from exc
    if not GIT_OID_RE.fullmatch(resolved):
        raise RescueError(f"{label} разрешился в неожиданный Git object id")
    return resolved


def optional_git_text(repo: Path, *arguments: str) -> str | None:
    try:
        value = run_git_text(repo, *arguments)
    except RescueError:
        return None
    return value.strip() or None


def parse_worktree_porcelain(text: str) -> list[dict[str, object]]:
    worktrees: list[dict[str, object]] = []
    current: dict[str, object] = {}

    for line in [*text.splitlines(), ""]:
        if not line:
            if current:
                worktrees.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            current["path"] = value
        elif key == "HEAD":
            current["head"] = value
        elif key == "branch":
            current["branch"] = value.removeprefix("refs/heads/")
        elif key in {"detached", "bare"}:
            current[key] = True
        elif key in {"locked", "prunable"}:
            current[key] = value or True
    return worktrees


def status_summary(repo: Path) -> dict[str, int]:
    lines = run_git_text(repo, "status", "--porcelain=v1", "--untracked-files=all").splitlines()
    counts = {"staged": 0, "unstaged": 0, "untracked": 0}
    for line in lines:
        if line.startswith("??"):
            counts["untracked"] += 1
            continue
        if len(line) >= 2 and line[0] != " ":
            counts["staged"] += 1
        if len(line) >= 2 and line[1] != " ":
            counts["unstaged"] += 1
    return counts


def git_context_for_cwd(raw_cwd: str | None) -> dict[str, object]:
    if not raw_cwd:
        return {"cwd_status": "unknown"}

    cwd = Path(raw_cwd).expanduser()
    if not cwd.exists():
        return {"cwd_status": "missing", "cwd": str(cwd)}
    if not cwd.is_dir():
        return {"cwd_status": "not_directory", "cwd": str(cwd)}

    try:
        repo_root = Path(run_git_text(cwd, "rev-parse", "--show-toplevel"))
    except RescueError as exc:
        return {"cwd_status": "not_git", "cwd": str(cwd), "detail": str(exc)}

    remote_lines = run_git_text(repo_root, "remote", "-v").splitlines()
    remotes: list[dict[str, str]] = []
    for line in remote_lines:
        parts = line.split()
        if len(parts) < 2:
            continue
        kind = parts[2].strip("()") if len(parts) >= 3 else "unknown"
        remotes.append(
            {"name": parts[0], "url": sanitize_remote_url(parts[1]), "kind": kind}
        )

    branch = optional_git_text(repo_root, "branch", "--show-current")
    return {
        "cwd_status": "ok",
        "cwd": str(cwd),
        "repo_root": str(repo_root),
        "git_common_dir": run_git_text(repo_root, "rev-parse", "--git-common-dir"),
        "branch": branch,
        "head": run_git_text(repo_root, "rev-parse", "HEAD"),
        "upstream": optional_git_text(
            repo_root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"
        ),
        "status": status_summary(repo_root),
        "remotes": remotes,
        "worktrees": parse_worktree_porcelain(
            run_git_text(repo_root, "worktree", "list", "--porcelain")
        ),
    }


def collect_working_directory_hints(
    value: object,
    hints: list[str],
    seen: set[str],
    *,
    depth: int = 0,
) -> bool:
    """Извлечь только поля cwd/workdir и JSON tool arguments без raw message text."""

    if depth > 12:
        return False

    def add_hint(raw_hint: str) -> bool:
        normalized = raw_hint.strip()
        if not normalized or normalized in seen:
            return False
        if len(hints) >= MAX_PATH_HINTS:
            return True
        seen.add(normalized)
        hints.append(normalized)
        return False

    def tool_input_hints(source: str) -> list[str]:
        extracted: list[str] = []
        for match in TOOL_PATH_LITERAL_RE.finditer(source):
            double_quoted, single_quoted = match.groups()
            literal = double_quoted if double_quoted is not None else single_quoted
            quote = '"' if double_quoted is not None else "'"
            try:
                if quote == '"':
                    decoded = json.loads(f'"{literal}"')
                else:
                    decoded = bytes(literal, "utf-8").decode("unicode_escape")
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            extracted.append(decoded)

        simplified = source.replace("\\\\", "\\").replace('\\"', '"').replace("\\'", "'")
        extracted.extend(match.group(0).strip() for match in WINDOWS_ABSOLUTE_PATH_RE.finditer(simplified))
        extracted.extend(match.group(1).strip() for match in POSIX_QUOTED_PATH_RE.finditer(simplified))
        return extracted

    truncated = False
    if isinstance(value, dict):
        for raw_key, item in value.items():
            key = str(raw_key).lower()
            if key in {"cwd", "workdir"} and isinstance(item, str):
                truncated = add_hint(item) or truncated
                continue
            if key in {"arguments", "input"} and isinstance(item, str) and item.lstrip().startswith(("{", "[")):
                try:
                    decoded = json.loads(item)
                except json.JSONDecodeError:
                    continue
                truncated = (
                    collect_working_directory_hints(
                        decoded, hints, seen, depth=depth + 1
                    )
                    or truncated
                )
                continue
            if key in {"arguments", "input"} and isinstance(item, str):
                for path_hint in tool_input_hints(item):
                    truncated = add_hint(path_hint) or truncated
                continue
            if isinstance(item, (dict, list)):
                truncated = (
                    collect_working_directory_hints(
                        item, hints, seen, depth=depth + 1
                    )
                    or truncated
                )
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)):
                truncated = (
                    collect_working_directory_hints(
                        item, hints, seen, depth=depth + 1
                    )
                    or truncated
                )
    return truncated


def git_candidates_from_hints(hints: Sequence[str]) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    seen_roots: set[str] = set()
    for hint in hints:
        hint_path = Path(hint).expanduser()
        if any(part.lower() in LOCAL_STATE_ROOTS for part in hint_path.parts):
            continue
        candidate_cwd = hint_path.parent if hint_path.is_file() else hint_path
        context = git_context_for_cwd(str(candidate_cwd))
        if context.get("cwd_status") != "ok":
            continue
        root = str(context["repo_root"])
        root_key = os.path.normcase(os.path.abspath(root))
        if root_key in seen_roots:
            continue
        seen_roots.add(root_key)
        candidates.append(context)
    return candidates


def inspect_session_file(
    path: Path, expected_thread_id: str, max_records: int
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "session_file": str(path),
        "archived": "archived_sessions" in {part.lower() for part in path.parts},
        "size": path.stat().st_size,
        "records_scanned": 0,
        "parse_errors": 0,
        "thread_id": None,
        "id_source": None,
        "cwd": None,
        "timestamp": None,
    }
    path_hints: list[str] = []
    seen_path_hints: set[str] = set()
    path_hints_truncated = False
    records_truncated = False

    try:
        with path.open("r", encoding="utf-8") as stream:
            for record_number, line in enumerate(stream, start=1):
                if record_number > max_records:
                    records_truncated = True
                    break
                metadata["records_scanned"] = record_number
                try:
                    record = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    metadata["parse_errors"] = int(metadata["parse_errors"]) + 1
                    continue
                if not isinstance(record, dict):
                    continue

                path_hints_truncated = (
                    collect_working_directory_hints(record, path_hints, seen_path_hints)
                    or path_hints_truncated
                )

                payload = record.get("payload")
                if not isinstance(payload, dict):
                    payload = {}

                if record.get("type") == "session_meta":
                    observed_id = payload.get("id") or record.get("id")
                    if isinstance(observed_id, str):
                        metadata["thread_id"] = observed_id
                        metadata["id_source"] = "session_meta"
                    observed_cwd = payload.get("cwd") or record.get("cwd")
                    if isinstance(observed_cwd, str):
                        metadata["cwd"] = observed_cwd
                    observed_timestamp = payload.get("timestamp") or record.get("timestamp")
                    if isinstance(observed_timestamp, str):
                        metadata["timestamp"] = observed_timestamp

                if metadata["cwd"] is None:
                    observed_cwd = payload.get("cwd") or record.get("cwd")
                    if isinstance(observed_cwd, str):
                        metadata["cwd"] = observed_cwd

    except (OSError, UnicodeDecodeError) as exc:
        raise RescueError(f"Не удалось прочитать session file {path}: {exc}") from exc

    if metadata["thread_id"] is None and expected_thread_id.lower() in path.name.lower():
        metadata["thread_id"] = expected_thread_id
        metadata["id_source"] = "filename"

    metadata["schema_status"] = (
        "confirmed" if metadata["id_source"] == "session_meta" else "schema_unconfirmed"
    )
    primary_cwd = metadata["cwd"] if isinstance(metadata["cwd"], str) else None
    if primary_cwd and primary_cwd not in seen_path_hints:
        path_hints.insert(0, primary_cwd)
    metadata["path_hints_observed"] = len(path_hints)
    metadata["path_hints_truncated"] = path_hints_truncated
    metadata["records_truncated"] = records_truncated
    metadata["discovery_status"] = (
        "partial" if records_truncated or path_hints_truncated else "complete"
    )
    metadata["git"] = git_context_for_cwd(
        primary_cwd
    )
    metadata["git_candidates"] = git_candidates_from_hints(path_hints)
    return metadata


def session_roots(codex_home: Path) -> list[Path]:
    return [codex_home / "sessions", codex_home / "archived_sessions"]


def all_session_files(codex_home: Path) -> list[Path]:
    files: list[Path] = []
    for root in session_roots(codex_home):
        if not root.is_dir():
            continue
        try:
            files.extend(root.rglob("*.jsonl"))
        except OSError as exc:
            raise RescueError(f"Не удалось просмотреть каталог sessions {root}: {exc}") from exc
    return sorted(set(files), key=lambda item: str(item).lower())


def load_session_index(codex_home: Path) -> dict[str, str]:
    index_path = codex_home / "session_index.jsonl"
    if not index_path.is_file():
        return {}

    titles: dict[str, str] = {}
    try:
        with index_path.open("r", encoding="utf-8") as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if not isinstance(row, dict):
                    continue
                thread_id = row.get("id")
                title = row.get("thread_name")
                if isinstance(thread_id, str) and isinstance(title, str) and title.strip():
                    titles[thread_id.lower()] = title.strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise RescueError(f"Не удалось прочитать session index {index_path}: {exc}") from exc
    return titles


def message_text(payload: dict[str, object]) -> str:
    content = payload.get("content")
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(str(item["text"]))
    return " ".join(parts)


def inspect_session_identity(
    path: Path,
    index_titles: dict[str, str],
    *,
    title_query: str | None,
    max_records: int = TARGET_TITLE_RECORD_LIMIT,
) -> dict[str, object]:
    thread_id: str | None = None
    thread_id_source: str | None = None
    filename_match = THREAD_ID_SEARCH_RE.search(path.name)
    if filename_match:
        thread_id = filename_match.group(0)
        thread_id_source = "filename"

    normalized_query = normalize_title(title_query) if title_query else None
    title_source: str | None = None
    observed_title: str | None = None
    indexed_title: str | None = None
    if thread_id and thread_id.lower() in index_titles:
        indexed_title = index_titles[thread_id.lower()]
        observed_title = indexed_title
        if normalized_query and normalize_title(observed_title) == normalized_query:
            title_source = "session_index"

    try:
        with path.open("r", encoding="utf-8") as stream:
            for record_number, line in enumerate(stream, start=1):
                if record_number > max_records:
                    break
                try:
                    record = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if not isinstance(record, dict):
                    continue
                payload = record.get("payload")
                if not isinstance(payload, dict):
                    payload = {}

                if record.get("type") == "session_meta":
                    observed_id = payload.get("id") or record.get("id")
                    if isinstance(observed_id, str):
                        thread_id = observed_id
                        thread_id_source = "session_meta"
                        indexed_title = index_titles.get(observed_id.lower())
                        if indexed_title:
                            observed_title = indexed_title
                            title_source = None
                            if normalized_query and normalize_title(indexed_title) == normalized_query:
                                title_source = "session_index"
                        else:
                            if title_source != "early_user_message":
                                observed_title = None
                                title_source = None

                if (
                    normalized_query
                    and indexed_title is None
                    and record.get("type") == "response_item"
                    and payload.get("type") == "message"
                    and payload.get("role") == "user"
                ):
                    observed_message = normalize_title(message_text(payload))
                    if normalized_query == observed_message:
                        observed_title = title_query
                        title_source = "early_user_message"

                if thread_id_source == "session_meta" and (
                    not normalized_query or title_source
                ):
                    break
        size_bytes = path.stat().st_size
    except (OSError, UnicodeDecodeError) as exc:
        raise RescueError(f"Не удалось прочитать session identity {path}: {exc}") from exc

    return {
        "thread_id": thread_id,
        "thread_id_source": thread_id_source,
        "session_file": str(path.absolute()),
        "archived": "archived_sessions" in {part.lower() for part in path.parts},
        "size_bytes": size_bytes,
        "size_mib": size_mib_rounded(size_bytes),
        "title": observed_title,
        "title_source": title_source,
    }


def resolve_session_target(
    codex_home: Path,
    *,
    thread_id: str | None = None,
    title: str | None = None,
    expected_size_mib: str | None = None,
    expected_bytes: int | None = None,
) -> dict[str, object]:
    if bool(thread_id) == bool(title):
        raise RescueError("Нужно указать ровно одно: thread_id или title")
    if thread_id and not THREAD_ID_RE.fullmatch(thread_id):
        raise RescueError("thread_id имеет неожиданный формат")
    if expected_bytes is not None and expected_bytes < 0:
        raise RescueError("expected_bytes не может быть отрицательным")
    expected_mib = parse_expected_size_mib(expected_size_mib)

    query: dict[str, object] = {}
    if thread_id:
        query["thread_id"] = thread_id
    if title:
        query["title"] = title
    if expected_mib is not None:
        query["expected_size_mib"] = str(expected_mib)
    if expected_bytes is not None:
        query["expected_bytes"] = expected_bytes
    if title and expected_mib is None and expected_bytes is None:
        return {
            "status": "identity_incomplete",
            "query": query,
            "detail": "Поиск по title требует expected_size_mib или expected_bytes; иначе target не блокируется.",
            "candidates": [],
        }

    index_titles = load_session_index(codex_home) if title else {}
    candidates: list[dict[str, object]] = []
    inspection_errors: list[dict[str, str]] = []
    session_files = all_session_files(codex_home)
    filename_matches: list[Path] = []
    if thread_id:
        filename_matches = [
            path
            for path in session_files
            if (match := THREAD_ID_SEARCH_RE.search(path.name))
            and match.group(0).lower() == thread_id.lower()
        ]

    def inspect_paths(paths: Sequence[Path]) -> None:
        for path in paths:
            try:
                identity = inspect_session_identity(
                    path,
                    index_titles,
                    title_query=title,
                )
            except RescueError as exc:
                inspection_errors.append(
                    {"session_file": str(path.resolve()), "detail": str(exc)}
                )
                continue
            observed_id = identity.get("thread_id")
            if (
                not isinstance(observed_id, str)
                or not THREAD_ID_RE.fullmatch(observed_id)
                or identity.get("thread_id_source") != "session_meta"
            ):
                inspection_errors.append(
                    {
                        "session_file": str(path.resolve()),
                        "detail": "Session candidate не подтверждает корректный thread_id через session_meta",
                    }
                )
                continue
            if thread_id and observed_id.lower() != thread_id.lower():
                continue
            if title and not identity.get("title_source"):
                continue
            if expected_bytes is not None and identity["size_bytes"] != expected_bytes:
                continue
            if expected_mib is not None and Decimal(str(identity["size_mib"])) != expected_mib:
                continue
            candidates.append(identity)

    if thread_id and filename_matches:
        inspect_paths(filename_matches)
        filename_match_set = set(filename_matches)
        remaining = [path for path in session_files if path not in filename_match_set]
        if candidates:
            duplicate_paths: list[Path] = []
            for path in remaining:
                try:
                    if session_file_declares_thread_id(
                        path,
                        thread_id,
                        TARGET_TITLE_RECORD_LIMIT,
                    ):
                        duplicate_paths.append(path)
                except RescueError as exc:
                    inspection_errors.append(
                        {"session_file": str(path.resolve()), "detail": str(exc)}
                    )
            inspect_paths(duplicate_paths)
        else:
            inspect_paths(remaining)
    else:
        inspect_paths(session_files)

    diagnostics = {"inspection_errors": inspection_errors} if inspection_errors else {}
    if not candidates:
        return {
            "status": "target_not_found",
            "query": query,
            "candidates": [],
            **diagnostics,
        }
    if len(candidates) > 1:
        return {
            "status": "ambiguous_target",
            "query": query,
            "candidates": candidates,
            **diagnostics,
        }
    return {
        "status": "resolved",
        "query": query,
        "target": candidates[0],
        **diagnostics,
    }


def target_identity(target: dict[str, object]) -> tuple[object, object, object]:
    return target.get("thread_id"), target.get("session_file"), target.get("archived")


def target_lock_payload(resolution: dict[str, object]) -> dict[str, object]:
    if resolution.get("status") != "resolved" or not isinstance(
        resolution.get("target"), dict
    ):
        raise RescueError("Target lock можно создать только из однозначного resolution")
    return {
        "version": TARGET_LOCK_VERSION,
        "kind": TARGET_LOCK_KIND,
        "query": resolution.get("query", {}),
        "target": resolution["target"],
    }


def load_target_lock(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RescueError(f"Не удалось прочитать target lock {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RescueError("Target lock должен быть JSON object")
    if payload.get("version") != TARGET_LOCK_VERSION or payload.get("kind") != TARGET_LOCK_KIND:
        raise RescueError("Target lock имеет неизвестную schema")
    target = payload.get("target")
    if not isinstance(target, dict):
        raise RescueError("Target lock не содержит target object")
    thread_id = target.get("thread_id")
    session_file = target.get("session_file")
    if not isinstance(thread_id, str) or not THREAD_ID_RE.fullmatch(thread_id):
        raise RescueError("Target lock содержит некорректный thread_id")
    if not isinstance(session_file, str) or not Path(session_file).is_absolute():
        raise RescueError("Target lock содержит не абсолютный session_file")
    return payload


def path_is_inside_git_worktree(path: Path) -> bool:
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(path.resolve().parent),
                "rev-parse",
                "--is-inside-work-tree",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise RescueError(f"Не удалось проверить каталог target lock через Git: {exc}") from exc
    return completed.returncode == 0 and completed.stdout.strip().lower() == b"true"


def write_target_lock(path: Path, payload: dict[str, object]) -> dict[str, object]:
    if path.name.lower() != "target-lock.json":
        raise RescueError("Target lock должен называться target-lock.json")
    if path_is_inside_git_worktree(path):
        raise RescueError("Target lock нельзя размещать внутри Git worktree")
    if path.exists():
        existing = load_target_lock(path)
        existing_target = existing.get("target")
        new_target = payload.get("target")
        if isinstance(existing_target, dict) and isinstance(new_target, dict):
            if target_identity(existing_target) == target_identity(new_target):
                return {"status": "target_locked", "lock_state": "reused"}
        return {
            "status": "target_lock_conflict",
            "lock_state": "unchanged",
            "invalidation_required": True,
            "active_target": existing_target,
            "rejected_target": new_target,
        }
    if not path.parent.is_dir():
        raise RescueError(f"Каталог для target lock не существует: {path.parent}")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except OSError as exc:
        raise RescueError(f"Не удалось записать target lock {path}: {exc}") from exc
    return {"status": "target_locked", "lock_state": "created"}


def path_is_under(path: Path, roots: Sequence[Path]) -> bool:
    resolved = path.resolve()
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            continue
        return True
    return False


def inventory_from_target_lock(
    codex_home: Path,
    lock_path: Path,
    *,
    max_records: int,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    if max_records < 1:
        raise RescueError("max_records должен быть положительным")
    lock = load_target_lock(lock_path)
    target = lock["target"]
    assert isinstance(target, dict)
    session_path = Path(str(target["session_file"]))
    if not path_is_under(session_path, session_roots(codex_home)):
        raise RescueError("Target lock указывает вне CODEX_HOME sessions")
    if not session_path.is_file():
        raise RescueError("Target lock session_file больше не существует; нужен новый resolution")

    thread_id = str(target["thread_id"])
    inspected = inspect_session_file(session_path, thread_id, max_records)
    if inspected.get("id_source") != "session_meta":
        raise RescueError("TARGET_LOCK_UNCONFIRMED: session_meta с thread_id не найден")
    if str(inspected.get("thread_id", "")).lower() != thread_id.lower():
        raise RescueError("TARGET_LOCK_MISMATCH: session file объявляет другой thread_id")
    if bool(target.get("archived")) != bool(inspected.get("archived")):
        raise RescueError("TARGET_LOCK_MISMATCH: archive state изменился")
    if target.get("archived") and inspected.get("size") != target.get("size_bytes"):
        raise RescueError("TARGET_LOCK_MISMATCH: размер архивной session изменился")
    return lock, [inspected]


def session_file_declares_thread_id(path: Path, thread_id: str, max_records: int) -> bool:
    """Дешёво проверить session_meta без Git discovery и разбора tool inputs."""

    try:
        with path.open("rb") as stream:
            for record_number, line in enumerate(stream, start=1):
                if record_number > max_records:
                    break
                if b"session_meta" not in line:
                    continue
                try:
                    record = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if not isinstance(record, dict) or record.get("type") != "session_meta":
                    continue
                payload = record.get("payload")
                if not isinstance(payload, dict):
                    payload = {}
                observed_id = payload.get("id") or record.get("id")
                return isinstance(observed_id, str) and observed_id.lower() == thread_id.lower()
    except OSError as exc:
        raise RescueError(f"Не удалось прочитать session file {path}: {exc}") from exc
    return False


def find_session_files(
    codex_home: Path,
    thread_id: str,
    *,
    max_records: int = 10000,
    scan_content: bool = False,
) -> list[dict[str, object]]:
    if not THREAD_ID_RE.fullmatch(thread_id):
        raise RescueError("thread_id имеет неожиданный формат")
    if max_records < 1:
        raise RescueError("max_records должен быть положительным")

    candidates: set[Path] = set()
    all_files: list[Path] = []
    for root in session_roots(codex_home):
        if not root.is_dir():
            continue
        try:
            files = list(root.rglob("*.jsonl"))
        except OSError as exc:
            raise RescueError(f"Не удалось просмотреть каталог sessions {root}: {exc}") from exc
        all_files.extend(files)
        candidates.update(path for path in files if thread_id.lower() in path.name.lower())

    if not candidates and scan_content:
        for path in all_files:
            if session_file_declares_thread_id(path, thread_id, max_records):
                candidates.add(path)

    results = [
        inspect_session_file(path, thread_id, max_records)
        for path in sorted(candidates, key=lambda item: str(item).lower())
    ]
    return [
        item
        for item in results
        if str(item.get("thread_id", "")).lower() == thread_id.lower()
    ]


def manifest_path(raw_path: object) -> PurePosixPath:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise RescueError("Manifest path должен быть непустой строкой")
    if "\\" in raw_path:
        raise RescueError(f"Manifest path должен использовать POSIX separator: {raw_path}")

    path = PurePosixPath(raw_path)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RescueError(f"Manifest path должен быть безопасным repo-relative path: {raw_path}")

    parts_lower = [part.lower() for part in path.parts]
    filename = parts_lower[-1]
    if any(part in LOCAL_STATE_ROOTS | {".git"} for part in parts_lower):
        raise RescueError(f"Manifest содержит локальное служебное состояние: {raw_path}")
    if filename in LOCAL_STATE_FILES or filename.startswith("rollout-") and filename.endswith(".jsonl"):
        raise RescueError(f"Manifest содержит raw session/state file: {raw_path}")
    if filename.startswith(".env"):
        raise RescueError(f"Manifest содержит credential-prone env file: {raw_path}")
    return path


def load_manifest(path: Path) -> list[dict[str, object]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RescueError(f"Не удалось прочитать JSON manifest {path}: {exc}") from exc

    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise RescueError("Manifest должен быть object с version=1")
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        raise RescueError("Manifest files должен быть непустым списком")

    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            raise RescueError(f"Manifest files[{index}] должен быть object")
        safe_path = manifest_path(item.get("path"))
        path_text = safe_path.as_posix()
        if path_text in seen:
            raise RescueError(f"Manifest содержит duplicate path: {path_text}")
        seen.add(path_text)

        digest = item.get("sha256")
        size = item.get("size")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise RescueError(f"Manifest содержит некорректный sha256: {path_text}")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise RescueError(f"Manifest содержит некорректный size: {path_text}")
        normalized.append({"path": path_text, "sha256": digest, "size": size})
    return normalized


def resolve_working_path(repo: Path, relative_path: str) -> Path:
    repo_resolved = repo.resolve()
    candidate = Path(os.path.abspath(repo / Path(*PurePosixPath(relative_path).parts)))
    try:
        candidate.relative_to(repo_resolved)
    except ValueError as exc:
        raise RescueError(f"Path вышел за границы repo: {relative_path}") from exc

    resolved_parent = candidate.parent.resolve()
    try:
        resolved_parent.relative_to(repo_resolved)
    except ValueError as exc:
        raise RescueError(f"Parent path вышел за границы repo: {relative_path}") from exc

    if candidate.is_symlink():
        return candidate

    resolved_candidate = candidate.resolve()
    try:
        resolved_candidate.relative_to(repo_resolved)
    except ValueError as exc:
        raise RescueError(f"Path вышел за границы repo через symlink: {relative_path}") from exc
    return resolved_candidate


def read_filesystem_bytes(repo: Path, relative_path: str) -> bytes:
    path = resolve_working_path(repo, relative_path)
    if path.is_symlink():
        return os.fsencode(os.readlink(path))
    return path.read_bytes()


@contextmanager
def fresh_checkout(repo: Path, commit: str) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="codex-session-rescue-") as temporary:
        checkout = Path(temporary) / "checkout"
        clone = subprocess.run(
            ["git", "clone", "--quiet", "--no-checkout", "--no-hardlinks", str(repo), str(checkout)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if clone.returncode != 0:
            message = clone.stderr.decode("utf-8", errors="replace").strip()
            raise RescueError(f"Не удалось создать fresh local clone: {message}")
        run_git_bytes(checkout, "checkout", "--quiet", "--detach", commit)
        yield checkout


def bytes_for_source(
    repo: Path,
    relative_path: str,
    source: str,
    *,
    commit: str,
    checkout_root: Path | None,
) -> bytes:
    if source == "working":
        return read_filesystem_bytes(repo, relative_path)
    if source == "index":
        return run_git_bytes(repo, "show", f":{relative_path}")
    if source == "commit":
        return run_git_bytes(repo, "show", f"{commit}:{relative_path}")
    if source == "checkout" and checkout_root is not None:
        return read_filesystem_bytes(checkout_root, relative_path)
    raise RescueError(f"Неизвестный byte source: {source}")


def decode_nul_paths(output: bytes) -> set[str]:
    paths: set[str] = set()
    for raw_path in output.split(b"\0"):
        if not raw_path:
            continue
        try:
            paths.add(raw_path.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise RescueError("Git вернул path, который не является UTF-8; exact scope не доказан") from exc
    return paths


def scope_diff_arguments(
    mode: str,
    *,
    commit: str,
    base: str,
    diff_filter: str | None = None,
) -> tuple[str, ...]:
    options = ["--name-only", "-z", "--no-renames"]
    if diff_filter:
        options.append(f"--diff-filter={diff_filter}")
    if mode == "index":
        return ("diff", "--cached", *options, base, "--")
    if mode == "commit":
        return ("diff", *options, base, commit, "--")
    raise RescueError("exact_scope должен быть index или commit")


def changed_paths_for_scope(
    repo: Path,
    mode: str,
    *,
    commit: str,
    base: str,
) -> dict[str, object]:
    all_paths = decode_nul_paths(
        run_git_bytes(
            repo,
            *scope_diff_arguments(mode, commit=commit, base=base),
        )
    )
    type_changes = decode_nul_paths(
        run_git_bytes(
            repo,
            *scope_diff_arguments(mode, commit=commit, base=base, diff_filter="T"),
        )
    )
    conflicts: set[str] = set()
    if mode == "index":
        conflicts = decode_nul_paths(
            run_git_bytes(
                repo,
                *scope_diff_arguments(mode, commit=commit, base=base, diff_filter="U"),
            )
        )
    unsupported_changes = [
        *({"status": "T", "path": path} for path in sorted(type_changes)),
        *({"status": "U", "path": path} for path in sorted(conflicts)),
    ]
    return {"paths": all_paths, "unsupported_changes": unsupported_changes}


def verify_manifest(
    repo: Path,
    entries: Sequence[dict[str, object]],
    sources: Sequence[str],
    *,
    commit: str = "HEAD",
    exact_scope: str | None = None,
    base: str | None = None,
) -> dict[str, object]:
    repo_root = Path(run_git_text(repo, "rev-parse", "--show-toplevel"))
    requested_sources = list(dict.fromkeys(sources))
    unknown_sources = sorted(set(requested_sources) - ALLOWED_SOURCES)
    if unknown_sources or not requested_sources:
        raise RescueError(
            "sources должен содержать working,index,commit или checkout; неизвестно: "
            + ",".join(unknown_sources)
        )
    if exact_scope and exact_scope not in requested_sources:
        raise RescueError(
            f"--exact-scope {exact_scope} требует --sources с byte source {exact_scope}"
        )

    commit_oid = resolve_commit(repo_root, commit, "commit")
    if exact_scope == "commit" and not base:
        raise RescueError("Для exact scope commit нужен --base с доказанным target tip")
    base_oid = resolve_commit(repo_root, base or "HEAD", "base") if exact_scope else None

    results: list[dict[str, object]] = []

    def verify_with_checkout(checkout_root: Path | None) -> None:
        for source in requested_sources:
            for entry in entries:
                relative_path = str(entry["path"])
                row: dict[str, object] = {
                    "source": source,
                    "path": relative_path,
                    "expected_sha256": entry["sha256"],
                    "expected_size": entry["size"],
                }
                try:
                    data = bytes_for_source(
                        repo_root,
                        relative_path,
                        source,
                        commit=commit_oid,
                        checkout_root=checkout_root,
                    )
                except (OSError, RescueError) as exc:
                    row.update({"status": "missing_or_unreadable", "detail": str(exc)})
                else:
                    actual_sha256 = sha256_bytes(data)
                    actual_size = len(data)
                    row.update(
                        {
                            "actual_sha256": actual_sha256,
                            "actual_size": actual_size,
                            "status": (
                                "ok"
                                if actual_sha256 == entry["sha256"]
                                and actual_size == entry["size"]
                                else "mismatch"
                            ),
                        }
                    )
                results.append(row)

    if "checkout" in requested_sources:
        with fresh_checkout(repo_root, commit_oid) as checkout_root:
            verify_with_checkout(checkout_root)
    else:
        verify_with_checkout(None)

    hash_status = "ok" if all(row["status"] == "ok" for row in results) else "mismatch"
    scope_report: dict[str, object]
    if exact_scope:
        expected_paths = {str(entry["path"]) for entry in entries}
        scope_evidence = changed_paths_for_scope(
            repo_root,
            exact_scope,
            commit=commit_oid,
            base=str(base_oid),
        )
        actual_paths = set(scope_evidence["paths"])
        unsupported_changes = list(scope_evidence["unsupported_changes"])
        unexpected = sorted(actual_paths - expected_paths)
        missing = sorted(expected_paths - actual_paths)
        scope_status = (
            "ok" if not unexpected and not missing and not unsupported_changes else "mismatch"
        )
        scope_report = {
            "status": scope_status,
            "mode": exact_scope,
            "base": base_oid,
            "unexpected_changed_paths": unexpected,
            "manifest_paths_not_changed": missing,
            "unsupported_changes": unsupported_changes,
        }
    else:
        scope_status = "unchecked"
        scope_report = {
            "status": "unchecked",
            "detail": "Проверены bytes manifest entries, но exact changed-path coverage не запрошен.",
        }

    if hash_status == "mismatch" or scope_status == "mismatch":
        status = "mismatch"
    elif scope_status == "ok":
        status = "ok"
    else:
        status = "hashes_ok_scope_unchecked"
    return {
        "status": status,
        "hash_status": hash_status,
        "scope": scope_report,
        "package_ready": status == "ok",
        "repo": str(repo_root),
        "commit": commit_oid,
        "sources": requested_sources,
        "files": results,
    }


def parse_sources(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Инвентаризация Codex-session и проверка evidence manifest."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve = subparsers.add_parser(
        "resolve-session", help="Однозначно разрешить task/session и создать target lock."
    )
    identity = resolve.add_mutually_exclusive_group(required=True)
    identity.add_argument("--thread-id", help="Точный Codex thread/task ID из native tool.")
    identity.add_argument("--title", help="Название task; при совпадениях нужен size gate.")
    size = resolve.add_mutually_exclusive_group()
    size.add_argument(
        "--expected-size-mib",
        help="Размер как в UI, округлённый до 0.01 MiB; запятая допустима.",
    )
    size.add_argument("--expected-bytes", type=int, help="Точный размер session file в bytes.")
    resolve.add_argument("--lock-file", type=Path, required=True, help="Новый immutable JSON lock.")
    resolve.add_argument(
        "--codex-home",
        type=Path,
        default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")),
        help="Корень Codex state; по умолчанию CODEX_HOME или ~/.codex.",
    )

    inventory = subparsers.add_parser(
        "inventory-session", help="Найти session file, cwd и связанный Git worktree."
    )
    inventory.add_argument(
        "--target-lock",
        type=Path,
        required=True,
        help="Lock, созданный resolve-session; свободный thread_id не принимается.",
    )
    inventory.add_argument(
        "--codex-home",
        type=Path,
        default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")),
        help="Корень Codex state; по умолчанию CODEX_HOME или ~/.codex.",
    )
    inventory.add_argument(
        "--max-records",
        type=int,
        default=10000,
        help="Максимум JSONL records для извлечения metadata из одного файла.",
    )

    verify = subparsers.add_parser(
        "verify-manifest", help="Сверить path, SHA256 и size по Git byte sources."
    )
    verify.add_argument("--repo", type=Path, default=Path.cwd(), help="Путь к Git repo.")
    verify.add_argument("--manifest", type=Path, required=True, help="JSON manifest version=1.")
    verify.add_argument(
        "--sources",
        default="working,index,commit,checkout",
        help="Список через запятую: working,index,commit,checkout.",
    )
    verify.add_argument("--commit", default="HEAD", help="Commit для sources commit и checkout.")
    verify.add_argument(
        "--exact-scope",
        choices=("index", "commit"),
        help="Сверить manifest paths с полным changed-path scope index или commit.",
    )
    verify.add_argument(
        "--base",
        help="Доказанный target tip; обязателен для --exact-scope commit, для index default=HEAD.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "resolve-session":
            resolution = resolve_session_target(
                args.codex_home,
                thread_id=args.thread_id,
                title=args.title,
                expected_size_mib=args.expected_size_mib,
                expected_bytes=args.expected_bytes,
            )
            if resolution["status"] != "resolved":
                print(json.dumps(resolution, ensure_ascii=False, indent=2))
                return 4 if resolution["status"] in {"ambiguous_target", "identity_incomplete"} else 3
            lock = target_lock_payload(resolution)
            lock_result = write_target_lock(args.lock_file, lock)
            payload = {
                **lock_result,
                "lock_file": str(args.lock_file.resolve()),
            }
            if lock_result["status"] == "target_locked":
                persisted_lock = load_target_lock(args.lock_file)
                payload["target"] = persisted_lock["target"]
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0 if lock_result["status"] == "target_locked" else 4

        if args.command == "inventory-session":
            lock, matches = inventory_from_target_lock(
                args.codex_home,
                args.target_lock,
                max_records=args.max_records,
            )
            target = lock["target"]
            assert isinstance(target, dict)
            payload = {
                "status": "found",
                "target_lock": str(args.target_lock.resolve()),
                "thread_id": target["thread_id"],
                "codex_home": str(args.codex_home),
                "matches": matches,
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        if args.command == "verify-manifest":
            entries = load_manifest(args.manifest)
            payload = verify_manifest(
                args.repo,
                entries,
                parse_sources(args.sources),
                commit=args.commit,
                exact_scope=args.exact_scope,
                base=args.base,
            )
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0 if payload["status"] != "mismatch" else 2
    except RescueError as exc:
        print(json.dumps({"status": "error", "detail": str(exc)}, ensure_ascii=False, indent=2))
        return 2

    parser.error("Неизвестная команда")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
