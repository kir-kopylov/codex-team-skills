#!/usr/bin/env python3
"""Проверяет идентичность, источники, граф и hash-chain реестра решений."""

from __future__ import annotations

import argparse
import csv
import hashlib
import heapq
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


QUESTION_HEADER = ("question_id", "question", "question_fingerprint")
ANSWER_HEADER = (
    "question_id",
    "status",
    "answer",
    "evidence",
    "depends_on",
    "semantic_review",
)
SOURCE_HEADER = (
    "source_id",
    "source_type",
    "availability",
    "locator",
    "content_hash",
    "observed_at",
)
STATE_FIELDS = ("status", "answer", "evidence", "depends_on", "semantic_review")
STATUS_ORDER = (
    "UNASSESSED",
    "ANSWERED",
    "DERIVED",
    "UNKNOWN",
    "PENDING_CONTEXT",
    "CONFLICT",
)
ALLOWED_STATUSES = set(STATUS_ORDER)
ACCEPTED_STATUSES = {"ANSWERED", "DERIVED"}
ROOT_CANDIDATE_STATUSES = {"UNASSESSED", "UNKNOWN", "CONFLICT"}
UNRESOLVED_STATUSES = ROOT_CANDIDATE_STATUSES | {"PENDING_CONTEXT"}
REVIEW_VALUES = {"NOT_REQUIRED", "UNREVIEWED", "REVIEWED"}
SOURCE_TYPES = {
    "user_turn",
    "file",
    "tool_output",
    "system_record",
    "delegation",
    "legacy_text",
    "expected_file",
    "expected_measurement",
}
SOURCE_AVAILABILITY = {"OBSERVED", "MISSING"}
HISTORY_ACTIONS = {"BASELINE", "UPDATE", "SEMANTIC_REVIEW"}
ID_RE = re.compile(r"[1-9][0-9]*")
SOURCE_ID_RE = re.compile(r"[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?")
HASH_RE = re.compile(r"sha256:[0-9a-f]{64}")
DEPENDENCY_TOKEN_RE = re.compile(r"([1-9][0-9]*)(?:-([1-9][0-9]*))?")
BRACKET_TOKEN_RE = re.compile(r"\[([^\[\]\r\n]*)\]")
REFERENCE_RE = re.compile(r"(evidence|needed|decision):(.+)")
PENDING_PREFIX = "[не хватает контекста для принятия решения]"
UNKNOWN_PREFIX = "не знаю —"
GENESIS_HASH = "GENESIS"


@dataclass(frozen=True)
class QuestionRow:
    question_id: int
    question: str
    question_fingerprint: str
    line: int


@dataclass(frozen=True)
class AnswerRow:
    question_id: int
    status: str
    answer: str
    evidence: str
    depends_on: str
    semantic_review: str
    line: int


@dataclass(frozen=True)
class SourceRow:
    source_id: str
    source_type: str
    availability: str
    locator: str
    content_hash: str
    observed_at: str
    line: int


@dataclass(frozen=True)
class RootImpact:
    question_id: int
    status: str
    dependent_pending_ids: tuple[int, ...]

    @property
    def impact(self) -> int:
        return len(self.dependent_pending_ids)


@dataclass(frozen=True)
class ValidationReport:
    errors: tuple[str, ...]
    status_counts: tuple[tuple[str, int], ...]
    unresolved_roots: tuple[RootImpact, ...]
    question_count: int
    unreviewed_accepted_ids: tuple[int, ...]


def canonical_question(text: str) -> str:
    """Нормализовать только пробелы и Unicode, не подменяя смысл вопроса."""

    return " ".join(unicodedata.normalize("NFC", text).split())


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def question_fingerprint(question: str) -> str:
    return sha256_text(canonical_question(question))


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compute_event_hash(event_without_hash: dict[str, Any]) -> str:
    return sha256_text(canonical_json(event_without_hash))


def answer_state(row: AnswerRow) -> dict[str, str]:
    return {field: getattr(row, field) for field in STATE_FIELDS}


def build_history_event(
    *,
    sequence: int,
    recorded_at: str,
    actor: str,
    action: str,
    question: QuestionRow,
    state: dict[str, str],
    previous_event_hash: str,
    review_basis: str | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "sequence": sequence,
        "recorded_at": recorded_at,
        "actor": actor,
        "action": action,
        "question_id": question.question_id,
        "question_fingerprint": question.question_fingerprint,
        "state": state,
        "previous_event_hash": previous_event_hash,
    }
    if review_basis is not None:
        event["review"] = {"reviewer": actor, "basis": review_basis}
    event["event_hash"] = compute_event_hash(event)
    return event


def _is_timezone_timestamp(value: str) -> bool:
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _read_rows(path: Path, *, delimiter: str) -> tuple[list[list[str]], list[str]]:
    if not path.is_file():
        return [], [f"файл не найден: {path}"]
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.reader(handle, delimiter=delimiter)), []
    except (OSError, UnicodeError, csv.Error) as error:
        return [], [f"не удалось прочитать {path}: {error}"]


def _parse_id(raw: str, *, label: str, errors: list[str]) -> int | None:
    value = raw.strip()
    if not ID_RE.fullmatch(value):
        errors.append(f"{label}: question_id должен быть положительным целым без ведущих нулей")
        return None
    return int(value)


def load_questions(path: Path) -> tuple[list[QuestionRow], list[str]]:
    raw_rows, errors = _read_rows(path, delimiter="\t")
    if errors:
        return [], errors
    if not raw_rows:
        return [], [f"{path}: пустой файл"]
    if tuple(raw_rows[0]) != QUESTION_HEADER:
        return [], [f"{path}: ожидается заголовок {list(QUESTION_HEADER)!r}"]

    rows: list[QuestionRow] = []
    for line, raw in enumerate(raw_rows[1:], start=2):
        if not raw or all(not cell.strip() for cell in raw):
            continue
        if len(raw) != len(QUESTION_HEADER):
            errors.append(f"{path}:{line}: ожидается 3 колонки, получено {len(raw)}")
            continue
        question_id = _parse_id(raw[0], label=f"{path}:{line}", errors=errors)
        question = canonical_question(raw[1])
        fingerprint = raw[2].strip()
        if not question:
            errors.append(f"{path}:{line}: question не может быть пустым")
        expected = question_fingerprint(question) if question else ""
        if fingerprint != expected:
            errors.append(
                f"{path}:{line}: question_fingerprint не совпадает с текстом; ожидается {expected!r}"
            )
        if question_id is not None and question and fingerprint == expected:
            rows.append(QuestionRow(question_id, question, fingerprint, line))
    if not rows:
        errors.append(f"{path}: нет ни одного корректного вопроса")
    return rows, errors


def load_answers(path: Path) -> tuple[list[AnswerRow], list[str]]:
    raw_rows, errors = _read_rows(path, delimiter=",")
    if errors:
        return [], errors
    if not raw_rows:
        return [], [f"{path}: пустой файл"]
    if tuple(raw_rows[0]) != ANSWER_HEADER:
        return [], [f"{path}: ожидается заголовок {list(ANSWER_HEADER)!r}"]

    rows: list[AnswerRow] = []
    for line, raw in enumerate(raw_rows[1:], start=2):
        if not raw or all(not cell.strip() for cell in raw):
            continue
        if len(raw) != len(ANSWER_HEADER):
            errors.append(f"{path}:{line}: ожидается 6 колонок, получено {len(raw)}")
            continue
        question_id = _parse_id(raw[0], label=f"{path}:{line}", errors=errors)
        if question_id is not None:
            rows.append(
                AnswerRow(
                    question_id,
                    raw[1].strip(),
                    raw[2].strip(),
                    raw[3].strip(),
                    raw[4].strip(),
                    raw[5].strip(),
                    line,
                )
            )
    if not rows:
        errors.append(f"{path}: нет ни одной корректной строки реестра")
    return rows, errors


def load_sources(path: Path) -> tuple[list[SourceRow], list[str]]:
    raw_rows, errors = _read_rows(path, delimiter=",")
    if errors:
        return [], errors
    if not raw_rows:
        return [], [f"{path}: пустой файл"]
    if tuple(raw_rows[0]) != SOURCE_HEADER:
        return [], [f"{path}: ожидается заголовок {list(SOURCE_HEADER)!r}"]

    rows: list[SourceRow] = []
    for line, raw in enumerate(raw_rows[1:], start=2):
        if not raw or all(not cell.strip() for cell in raw):
            continue
        if len(raw) != len(SOURCE_HEADER):
            errors.append(f"{path}:{line}: ожидается 6 колонок, получено {len(raw)}")
            continue
        row = SourceRow(*(cell.strip() for cell in raw), line=line)
        if not SOURCE_ID_RE.fullmatch(row.source_id):
            errors.append(f"{path}:{line}: некорректный source_id {row.source_id!r}")
        if row.source_type not in SOURCE_TYPES:
            errors.append(f"{path}:{line}: неизвестный source_type {row.source_type!r}")
        if row.availability not in SOURCE_AVAILABILITY:
            errors.append(f"{path}:{line}: неизвестный availability {row.availability!r}")
        if not row.locator:
            errors.append(f"{path}:{line}: locator не может быть пустым")
        if row.availability == "OBSERVED":
            if not HASH_RE.fullmatch(row.content_hash):
                errors.append(f"{path}:{line}: OBSERVED требует content_hash sha256")
            if not _is_timezone_timestamp(row.observed_at):
                errors.append(f"{path}:{line}: OBSERVED требует observed_at с часовым поясом")
        elif row.availability == "MISSING":
            if row.content_hash:
                errors.append(f"{path}:{line}: MISSING не может иметь content_hash")
            if row.observed_at:
                errors.append(f"{path}:{line}: MISSING не может иметь observed_at")
        rows.append(row)
    return rows, errors


def load_history(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    if not path.is_file():
        return [], [f"файл не найден: {path}"]
    events: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as error:
        return [], [f"не удалось прочитать {path}: {error}"]
    for line_number, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            errors.append(f"{path}:{line_number}: некорректный JSON: {error.msg}")
            continue
        if not isinstance(value, dict):
            errors.append(f"{path}:{line_number}: событие должно быть JSON object")
            continue
        value["_line"] = line_number
        events.append(value)
    if not events:
        errors.append(f"{path}: история не содержит событий")
    return events, errors


def expand_id_expression(
    raw: str,
    *,
    valid_ids: set[int],
    label: str,
    errors: list[str],
    empty_allowed: bool = True,
) -> list[int]:
    """Развернуть выражение только через существующие ID, без range-allocation."""

    expression = raw.strip()
    if not expression:
        if not empty_allowed:
            errors.append(f"{label}: список ID не может быть пустым")
        return []
    sorted_valid = sorted(valid_ids)
    expanded: list[int] = []
    for raw_token in expression.split(";"):
        token = raw_token.strip()
        match = DEPENDENCY_TOKEN_RE.fullmatch(token)
        if not match:
            errors.append(f"{label}: некорректный ID или диапазон {token!r}")
            continue
        start = int(match.group(1))
        end = int(match.group(2) or match.group(1))
        if start > end:
            errors.append(f"{label}: начало диапазона {start}-{end} больше конца")
            continue
        selected = [question_id for question_id in sorted_valid if start <= question_id <= end]
        if not selected:
            errors.append(f"{label}: диапазон {token!r} не содержит существующих ID")
            continue
        expanded.extend(selected)
    duplicates = sorted(item for item, count in Counter(expanded).items() if count > 1)
    if duplicates:
        errors.append(
            f"{label}: ID повторяются после разворачивания диапазонов: "
            + ", ".join(map(str, duplicates))
        )
    return list(dict.fromkeys(expanded))


def _parse_references(
    evidence: str,
    *,
    valid_ids: set[int],
    label: str,
    errors: list[str],
) -> tuple[set[str], set[str], set[int]]:
    evidence_ids: set[str] = set()
    needed_ids: set[str] = set()
    decision_ids: set[int] = set()
    seen_spans: set[tuple[int, int]] = set()

    for match in BRACKET_TOKEN_RE.finditer(evidence):
        seen_spans.add(match.span())
        token = match.group(1).strip()
        ref_match = REFERENCE_RE.fullmatch(token)
        if not ref_match:
            errors.append(f"{label}: неизвестная или повреждённая ссылка [{token}]")
            continue
        kind, value = ref_match.group(1), ref_match.group(2).strip()
        if kind in {"evidence", "needed"}:
            if not SOURCE_ID_RE.fullmatch(value):
                errors.append(f"{label}: некорректный source_id в [{token}]")
                continue
            target = evidence_ids if kind == "evidence" else needed_ids
            if value in target:
                errors.append(f"{label}: повторная ссылка [{token}]")
            target.add(value)
        else:
            ref_errors: list[str] = []
            expanded = expand_id_expression(
                value,
                valid_ids=valid_ids,
                label=f"{label}, decision",
                errors=ref_errors,
                empty_allowed=False,
            )
            errors.extend(ref_errors)
            decision_ids.update(expanded)

    if "[" in evidence or "]" in evidence:
        scrubbed = BRACKET_TOKEN_RE.sub("", evidence)
        if "[" in scrubbed or "]" in scrubbed:
            errors.append(f"{label}: незакрытая или вложенная квадратная скобка")
    return evidence_ids, needed_ids, decision_ids


def _duplicates(rows: list[Any], *, key: str, label: str) -> list[str]:
    positions: dict[Any, list[int]] = defaultdict(list)
    for row in rows:
        positions[getattr(row, key)].append(row.line)
    return [
        f"{label}: {key} {value!r} повторяется в строках " + ", ".join(map(str, positions[value]))
        for value in sorted(positions, key=str)
        if len(positions[value]) > 1
    ]


def _validate_answer_row(
    row: AnswerRow,
    *,
    valid_ids: set[int],
    sources: dict[str, SourceRow],
    label: str,
    errors: list[str],
) -> tuple[tuple[int, ...], set[int]]:
    dependency_errors: list[str] = []
    dependency_ids = expand_id_expression(
        row.depends_on,
        valid_ids=valid_ids,
        label=f"{label}, depends_on",
        errors=dependency_errors,
    )
    errors.extend(dependency_errors)
    refs_before = len(errors)
    evidence_ids, needed_ids, decision_ids = _parse_references(
        row.evidence,
        valid_ids=valid_ids,
        label=f"{label}, evidence",
        errors=errors,
    )

    for source_id in sorted(evidence_ids | needed_ids):
        if source_id not in sources:
            errors.append(f"{label}: ссылка ведёт на отсутствующий source_id {source_id!r}")
    observed_evidence: set[str] = set()
    for source_id in evidence_ids:
        source = sources.get(source_id)
        if source and source.availability != "OBSERVED":
            errors.append(f"{label}: MISSING source {source_id!r} нельзя использовать как evidence")
        elif source:
            observed_evidence.add(source_id)
    for source_id in needed_ids:
        source = sources.get(source_id)
        if source and source.availability != "MISSING":
            errors.append(f"{label}: needed source {source_id!r} должен иметь availability MISSING")

    if row.status not in ALLOWED_STATUSES:
        errors.append(f"{label}: неизвестный status {row.status!r}")
        return tuple(dependency_ids), decision_ids
    if row.semantic_review not in REVIEW_VALUES:
        errors.append(f"{label}: неизвестный semantic_review {row.semantic_review!r}")

    if row.status in ACCEPTED_STATUSES:
        if row.semantic_review not in {"UNREVIEWED", "REVIEWED"}:
            errors.append(f"{label}: {row.status} требует semantic_review UNREVIEWED или REVIEWED")
    elif row.semantic_review != "NOT_REQUIRED":
        errors.append(f"{label}: {row.status} требует semantic_review NOT_REQUIRED")

    if row.status == "UNASSESSED":
        if row.answer:
            errors.append(f"{label}: UNASSESSED требует пустой answer")
        if row.evidence:
            errors.append(f"{label}: UNASSESSED требует пустой evidence")
        return tuple(dependency_ids), decision_ids

    if not row.answer:
        errors.append(f"{label}: {row.status} требует непустой answer")
    if not row.evidence:
        errors.append(f"{label}: {row.status} требует непустой evidence")
    elif len(errors) == refs_before and not (evidence_ids or needed_ids or decision_ids):
        errors.append(f"{label}: evidence не содержит разрешимых ссылок")

    if row.status == "ANSWERED":
        if not observed_evidence:
            errors.append(f"{label}: ANSWERED требует хотя бы один OBSERVED evidence source")
        if needed_ids:
            errors.append(f"{label}: ANSWERED не может ссылаться на needed source")
    elif row.status == "DERIVED":
        delegation = any(
            sources[source_id].source_type == "delegation"
            for source_id in observed_evidence
            if source_id in sources
        )
        legacy_unreviewed = row.semantic_review == "UNREVIEWED" and any(
            sources[source_id].source_type == "legacy_text"
            for source_id in observed_evidence
            if source_id in sources
        )
        if not decision_ids and not delegation and not legacy_unreviewed:
            errors.append(f"{label}: DERIVED требует decision-ссылку или OBSERVED delegation")
        if decision_ids != set(dependency_ids):
            errors.append(f"{label}: decision-ссылки DERIVED должны точно совпадать с depends_on")
        if needed_ids:
            errors.append(f"{label}: DERIVED не может ссылаться на needed source")
    elif row.status == "UNKNOWN":
        if not row.answer.casefold().startswith(UNKNOWN_PREFIX):
            errors.append(f"{label}: UNKNOWN answer должен начинаться с {UNKNOWN_PREFIX!r}")
        elif not row.answer[len(UNKNOWN_PREFIX) :].strip():
            errors.append(f"{label}: UNKNOWN должен назвать неизвестный факт и способ его установить")
        if not needed_ids:
            errors.append(f"{label}: UNKNOWN требует хотя бы один MISSING needed source")
        if decision_ids:
            errors.append(f"{label}: UNKNOWN не может маскировать решение decision-ссылкой")
    elif row.status == "PENDING_CONTEXT":
        if not row.answer.startswith(PENDING_PREFIX):
            errors.append(f"{label}: PENDING_CONTEXT answer должен начинаться с точной метки")
        elif not row.answer[len(PENDING_PREFIX) :].strip():
            errors.append(f"{label}: PENDING_CONTEXT должен объяснить, чего не хватает")
        if not dependency_ids:
            errors.append(f"{label}: PENDING_CONTEXT требует непустой depends_on")
        if decision_ids != set(dependency_ids):
            errors.append(f"{label}: decision-ссылки PENDING_CONTEXT должны точно совпадать с depends_on")
        if needed_ids:
            errors.append(f"{label}: PENDING_CONTEXT должен зависеть от UNKNOWN ID, а не от needed source напрямую")
    elif row.status == "CONFLICT":
        legacy_unreviewed = row.semantic_review == "NOT_REQUIRED" and any(
            sources[source_id].source_type == "legacy_text"
            for source_id in observed_evidence
            if source_id in sources
        )
        if len(observed_evidence) < 2 and not legacy_unreviewed:
            errors.append(f"{label}: CONFLICT требует не меньше двух OBSERVED evidence sources")
        if needed_ids:
            errors.append(f"{label}: CONFLICT не может использовать MISSING source как сторону конфликта")

    return tuple(dependency_ids), decision_ids


def _cycle_nodes(dependencies: dict[int, tuple[int, ...]]) -> tuple[int, ...]:
    indegree = {node: 0 for node in dependencies}
    outgoing = {node: tuple(dep for dep in deps if dep in dependencies) for node, deps in dependencies.items()}
    for deps in outgoing.values():
        for dependency in deps:
            indegree[dependency] += 1
    queue = [node for node, degree in indegree.items() if degree == 0]
    heapq.heapify(queue)
    removed = 0
    while queue:
        node = heapq.heappop(queue)
        removed += 1
        for dependency in outgoing[node]:
            indegree[dependency] -= 1
            if indegree[dependency] == 0:
                heapq.heappush(queue, dependency)
    if removed == len(indegree):
        return ()
    return tuple(sorted(node for node, degree in indegree.items() if degree > 0))


def _roots_for_pending_iterative(
    pending_id: int,
    *,
    answers: dict[int, AnswerRow],
    dependencies: dict[int, tuple[int, ...]],
) -> frozenset[int]:
    roots: set[int] = set()
    visited: set[int] = set()
    stack = list(reversed(dependencies.get(pending_id, ())))
    while stack:
        candidate = stack.pop()
        if candidate in visited:
            continue
        visited.add(candidate)
        row = answers.get(candidate)
        if row is None or row.status not in UNRESOLVED_STATUSES:
            continue
        unresolved_dependencies = [
            dependency
            for dependency in dependencies.get(candidate, ())
            if dependency in answers and answers[dependency].status in UNRESOLVED_STATUSES
        ]
        if unresolved_dependencies:
            stack.extend(reversed(unresolved_dependencies))
        elif row.status in ROOT_CANDIDATE_STATUSES:
            roots.add(candidate)
    return frozenset(roots)


def _validate_history(
    events: list[dict[str, Any]],
    *,
    questions: dict[int, QuestionRow],
    answers: dict[int, AnswerRow],
    sources: dict[str, SourceRow],
    errors: list[str],
) -> None:
    expected_previous = GENESIS_HASH
    previous_recorded_at: datetime | None = None
    last_state: dict[int, dict[str, str]] = {}
    seen_ids: set[int] = set()
    valid_ids = set(questions)

    for expected_sequence, event in enumerate(events, start=1):
        line = event.get("_line", expected_sequence)
        payload = {key: value for key, value in event.items() if key not in {"event_hash", "_line"}}
        required = {
            "sequence",
            "recorded_at",
            "actor",
            "action",
            "question_id",
            "question_fingerprint",
            "state",
            "previous_event_hash",
        }
        missing = sorted(required - payload.keys())
        if missing:
            errors.append(f"history:{line}: отсутствуют поля: {', '.join(missing)}")
            continue
        if event.get("sequence") != expected_sequence:
            errors.append(f"history:{line}: sequence должен быть {expected_sequence}")
        recorded_at_value = str(event.get("recorded_at", ""))
        if not _is_timezone_timestamp(recorded_at_value):
            errors.append(f"history:{line}: recorded_at требует часовой пояс")
        else:
            parsed_recorded_at = datetime.fromisoformat(recorded_at_value.replace("Z", "+00:00"))
            if previous_recorded_at is not None and parsed_recorded_at < previous_recorded_at:
                errors.append(f"history:{line}: recorded_at меньше времени предыдущего события")
            previous_recorded_at = parsed_recorded_at
        if not isinstance(event.get("actor"), str) or not event["actor"].strip():
            errors.append(f"history:{line}: actor должен быть непустой строкой")
        action = event.get("action")
        if action not in HISTORY_ACTIONS:
            errors.append(f"history:{line}: неизвестный action {action!r}")
        if event.get("previous_event_hash") != expected_previous:
            errors.append(f"history:{line}: previous_event_hash не совпадает с предыдущим событием")
        actual_hash = event.get("event_hash")
        expected_hash = compute_event_hash(payload)
        if actual_hash != expected_hash:
            errors.append(f"history:{line}: event_hash не совпадает с содержимым события")
        if isinstance(actual_hash, str):
            expected_previous = actual_hash

        question_id = event.get("question_id")
        if not isinstance(question_id, int) or question_id not in questions:
            errors.append(f"history:{line}: отсутствующий или некорректный question_id {question_id!r}")
            continue
        question = questions[question_id]
        if event.get("question_fingerprint") != question.question_fingerprint:
            errors.append(f"history:{line}: fingerprint ID {question_id} не совпадает с индексом")
        state = event.get("state")
        if not isinstance(state, dict) or set(state) != set(STATE_FIELDS):
            errors.append(f"history:{line}: state должен содержать ровно {', '.join(STATE_FIELDS)}")
            continue
        if not all(isinstance(state[field], str) for field in STATE_FIELDS):
            errors.append(f"history:{line}: все поля state должны быть строками")
            continue
        historical_row = AnswerRow(question_id, *(state[field] for field in STATE_FIELDS), line=line)
        _validate_answer_row(
            historical_row,
            valid_ids=valid_ids,
            sources=sources,
            label=f"history:{line}, ID {question_id}",
            errors=errors,
        )

        previous_state = last_state.get(question_id)
        if previous_state is None:
            if action != "BASELINE":
                errors.append(f"history:{line}: первое событие ID {question_id} должно быть BASELINE")
            if state["status"] in ACCEPTED_STATUSES and state["semantic_review"] == "REVIEWED":
                errors.append(f"history:{line}: BASELINE принятой строки должен начинаться с UNREVIEWED")
        elif action == "BASELINE":
            errors.append(f"history:{line}: повторный BASELINE для ID {question_id}")
        elif action == "UPDATE":
            if state == previous_state:
                errors.append(f"history:{line}: UPDATE не изменяет state")
            required_review = "UNREVIEWED" if state["status"] in ACCEPTED_STATUSES else "NOT_REQUIRED"
            if state["semantic_review"] != required_review:
                errors.append(f"history:{line}: UPDATE должен сбросить semantic_review в {required_review}")
            if "review" in event:
                errors.append(f"history:{line}: UPDATE не должен содержать review")
        elif action == "SEMANTIC_REVIEW":
            previous_without_review = {key: value for key, value in previous_state.items() if key != "semantic_review"}
            state_without_review = {key: value for key, value in state.items() if key != "semantic_review"}
            if previous_without_review != state_without_review:
                errors.append(f"history:{line}: SEMANTIC_REVIEW не может менять ответ или зависимости")
            if previous_state.get("semantic_review") != "UNREVIEWED" or state.get("semantic_review") != "REVIEWED":
                errors.append(f"history:{line}: SEMANTIC_REVIEW должен переводить UNREVIEWED -> REVIEWED")
            review = event.get("review")
            if not isinstance(review, dict) or set(review) != {"reviewer", "basis"}:
                errors.append(f"history:{line}: SEMANTIC_REVIEW требует reviewer и basis")
            elif review.get("reviewer") != event.get("actor") or not str(review.get("basis", "")).strip():
                errors.append(f"history:{line}: reviewer должен совпадать с actor, basis не может быть пустым")
        last_state[question_id] = dict(state)
        seen_ids.add(question_id)

    missing_history = sorted(set(questions) - seen_ids)
    if missing_history:
        errors.append("history: нет BASELINE/событий для ID: " + ", ".join(map(str, missing_history)))
    extra_history = sorted(seen_ids - set(answers))
    if extra_history:
        errors.append("history: есть события без текущей строки ID: " + ", ".join(map(str, extra_history)))
    for question_id in sorted(set(answers) & set(last_state)):
        if last_state[question_id] != answer_state(answers[question_id]):
            errors.append(f"history: последнее state ID {question_id} не совпадает с answer-register.csv")


def validate_rows(
    questions: list[QuestionRow],
    answers: list[AnswerRow],
    sources: list[SourceRow],
    history: list[dict[str, Any]],
    *,
    initial_errors: list[str] | None = None,
    require_reviewed: bool = False,
) -> ValidationReport:
    errors = list(initial_errors or [])
    errors.extend(_duplicates(questions, key="question_id", label="индекс вопросов"))
    errors.extend(_duplicates(answers, key="question_id", label="реестр ответов"))
    errors.extend(_duplicates(sources, key="source_id", label="manifest источников"))

    question_order = [row.question_id for row in questions]
    answer_order = [row.question_id for row in answers]
    question_ids = set(question_order)
    answer_ids = set(answer_order)
    if question_ids - answer_ids:
        errors.append("в реестре нет ID: " + ", ".join(map(str, sorted(question_ids - answer_ids))))
    if answer_ids - question_ids:
        errors.append("в реестре есть лишние ID: " + ", ".join(map(str, sorted(answer_ids - question_ids))))
    if question_order != answer_order and question_ids == answer_ids and len(question_order) == len(answer_order):
        errors.append("порядок ID в реестре не совпадает с индексом вопросов")

    source_map = {row.source_id: row for row in sources}
    answer_map: dict[int, AnswerRow] = {}
    dependencies: dict[int, tuple[int, ...]] = {}
    for row in answers:
        answer_map.setdefault(row.question_id, row)
        deps, _ = _validate_answer_row(
            row,
            valid_ids=question_ids,
            sources=source_map,
            label=f"answer:{row.line}, ID {row.question_id}",
            errors=errors,
        )
        dependencies.setdefault(row.question_id, deps)

    cycle_nodes = _cycle_nodes(dependencies)
    if cycle_nodes:
        errors.append("граф зависимостей содержит цикл; заблокированные ID: " + ", ".join(map(str, cycle_nodes)))
    else:
        for row in answers:
            if row.status not in ACCEPTED_STATUSES:
                continue
            unresolved = sorted(
                dependency
                for dependency in dependencies.get(row.question_id, ())
                if dependency in answer_map and answer_map[dependency].status in UNRESOLVED_STATUSES
            )
            if unresolved:
                errors.append(
                    f"answer:{row.line}, ID {row.question_id}: принятый status зависит от незакрытых ID "
                    + ", ".join(map(str, unresolved))
                )

    pending_roots: dict[int, frozenset[int]] = {}
    if not cycle_nodes:
        for row in sorted(answers, key=lambda item: item.question_id):
            if row.status != "PENDING_CONTEXT":
                continue
            roots = _roots_for_pending_iterative(
                row.question_id,
                answers=answer_map,
                dependencies=dependencies,
            )
            pending_roots[row.question_id] = roots
            if not roots:
                errors.append(
                    f"answer:{row.line}, ID {row.question_id}: PENDING_CONTEXT не имеет пути до корня UNASSESSED, UNKNOWN или CONFLICT"
                )

    question_map = {row.question_id: row for row in questions}
    _validate_history(
        history,
        questions=question_map,
        answers=answer_map,
        sources=source_map,
        errors=errors,
    )

    dependents_by_root: dict[int, set[int]] = defaultdict(set)
    for pending_id, roots in pending_roots.items():
        for root_id in roots:
            dependents_by_root[root_id].add(pending_id)
    unresolved_roots = [
        RootImpact(
            question_id=root_id,
            status=answer_map[root_id].status,
            dependent_pending_ids=tuple(sorted(pending_ids)),
        )
        for root_id, pending_ids in dependents_by_root.items()
    ]
    unresolved_roots.sort(key=lambda item: (-item.impact, item.question_id))

    unreviewed = tuple(
        sorted(row.question_id for row in answers if row.status in ACCEPTED_STATUSES and row.semantic_review != "REVIEWED")
    )
    if require_reviewed and unreviewed:
        errors.append("semantic review не зафиксирован для принятых ID: " + ", ".join(map(str, unreviewed)))

    counts = Counter(row.status for row in answers if row.status in ALLOWED_STATUSES)
    return ValidationReport(
        errors=tuple(errors),
        status_counts=tuple((status, counts.get(status, 0)) for status in STATUS_ORDER),
        unresolved_roots=tuple(unresolved_roots),
        question_count=len(questions),
        unreviewed_accepted_ids=unreviewed,
    )


def validate_files(
    question_index: Path,
    answer_register: Path,
    source_manifest: Path,
    decision_history: Path,
    *,
    require_reviewed: bool = False,
) -> ValidationReport:
    questions, question_errors = load_questions(question_index)
    answers, answer_errors = load_answers(answer_register)
    sources, source_errors = load_sources(source_manifest)
    history, history_errors = load_history(decision_history)
    return validate_rows(
        questions,
        answers,
        sources,
        history,
        initial_errors=question_errors + answer_errors + source_errors + history_errors,
        require_reviewed=require_reviewed,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", required=True, type=Path)
    parser.add_argument("--answers", required=True, type=Path)
    parser.add_argument("--sources", required=True, type=Path)
    parser.add_argument("--history", required=True, type=Path)
    parser.add_argument("--require-reviewed", action="store_true")
    args = parser.parse_args(argv)

    for path in (args.questions, args.answers, args.sources, args.history):
        if not path.is_absolute():
            print(f"ОШИБКА: входной путь должен быть абсолютным: {path}", file=sys.stderr)
            return 2

    report = validate_files(
        args.questions,
        args.answers,
        args.sources,
        args.history,
        require_reviewed=args.require_reviewed,
    )
    if report.errors:
        for error in report.errors:
            print(f"ОШИБКА: {error}", file=sys.stderr)
        return 1

    print(f"Реестр структурно корректен: вопросов {report.question_count}.")
    print("Статусы: " + ", ".join(f"{status}={count}" for status, count in report.status_counts))
    if report.unresolved_roots:
        print("Корни незнания по разблокирующему охвату:")
        for root in report.unresolved_roots:
            dependents = ",".join(map(str, root.dependent_pending_ids))
            print(f"- ID {root.question_id}: status={root.status}; pending={root.impact}; dependent_ids={dependents}")
    else:
        print("Корни незнания, блокирующие PENDING_CONTEXT: нет.")
    if report.unreviewed_accepted_ids:
        ids = ",".join(map(str, report.unreviewed_accepted_ids))
        print(f"Готовность: STRUCTURALLY_VALID_SEMANTICALLY_UNREVIEWED; IDs={ids}.")
    else:
        print("Готовность: STRUCTURALLY_VALID_REVIEW_RECORDED.")
    print("Hash-chain делает переписывание обнаружимым внутри переданной истории, но не заменяет внешнюю подпись или удалённый anchor.")
    print("Валидатор не доказывает истинность внешних источников или качество смысловой проверки.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
