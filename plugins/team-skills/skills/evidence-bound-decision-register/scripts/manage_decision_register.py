#!/usr/bin/env python3
"""Мигрирует и изменяет реестр только вместе с append-only hash-chain."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import validate_decision_register as contract  # noqa: E402


LEGACY_QUESTION_HEADER = ("question_id", "question")
LEGACY_ANSWER_HEADER = ("question_id", "status", "answer", "evidence", "depends_on")


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _csv_text(header: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    import io

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(header)
    writer.writerows(rows)
    return output.getvalue()


def _tsv_text(header: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    import io

    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter="\t")
    writer.writerow(header)
    writer.writerows(rows)
    return output.getvalue()


def _history_text(events: list[dict]) -> str:
    return "".join(contract.canonical_json(event) + "\n" for event in events)


def _require_absolute(paths: list[Path]) -> None:
    relative = [str(path) for path in paths if not path.is_absolute()]
    if relative:
        raise ValueError("пути должны быть абсолютными: " + ", ".join(relative))


def _legacy_rows(path: Path, header: tuple[str, ...], delimiter: str) -> list[list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle, delimiter=delimiter))
    if not rows or tuple(rows[0]) != header:
        raise ValueError(f"{path}: ожидается legacy-заголовок {list(header)!r}")
    width = len(header)
    for line, row in enumerate(rows[1:], start=2):
        if len(row) != width:
            raise ValueError(f"{path}:{line}: ожидается {width} колонок")
    return rows[1:]


def migrate_legacy(
    legacy_questions: Path,
    legacy_answers: Path,
    out_dir: Path,
    *,
    actor: str,
    recorded_at: str,
) -> contract.ValidationReport:
    _require_absolute([legacy_questions, legacy_answers, out_dir])
    if not actor.strip() or not contract._is_timezone_timestamp(recorded_at):
        raise ValueError("actor и recorded_at с часовым поясом обязательны")
    if out_dir.exists() and any(out_dir.iterdir()):
        raise ValueError(f"выходная папка не пуста: {out_dir}")

    legacy_q = _legacy_rows(legacy_questions, LEGACY_QUESTION_HEADER, "\t")
    legacy_a = _legacy_rows(legacy_answers, LEGACY_ANSWER_HEADER, ",")
    questions: list[contract.QuestionRow] = []
    for line, raw in enumerate(legacy_q, start=2):
        if not contract.ID_RE.fullmatch(raw[0].strip()):
            raise ValueError(f"legacy questions:{line}: некорректный ID")
        question_id = int(raw[0])
        question = contract.canonical_question(raw[1])
        questions.append(
            contract.QuestionRow(question_id, question, contract.question_fingerprint(question), line)
        )
    if [row.question_id for row in questions] != [int(row[0]) for row in legacy_a]:
        raise ValueError("legacy index и register должны иметь одинаковый упорядоченный набор ID")

    sources: list[contract.SourceRow] = []
    answers: list[contract.AnswerRow] = []
    report_rows: list[tuple[str, ...]] = []
    for line, (question, raw) in enumerate(zip(questions, legacy_a), start=2):
        _, status, answer, legacy_evidence, depends_on = (cell.strip() for cell in raw)
        refs: list[str] = []
        if answer:
            source_id = f"legacy-answer-q{question.question_id}"
            sources.append(
                contract.SourceRow(
                    source_id,
                    "legacy_text",
                    "OBSERVED",
                    f"legacy:{legacy_answers.name}#answer-row-{line}",
                    contract.sha256_text(answer),
                    recorded_at,
                    len(sources) + 2,
                )
            )
            refs.append(f"[evidence:{source_id}]")
        if legacy_evidence:
            source_id = f"legacy-evidence-q{question.question_id}"
            sources.append(
                contract.SourceRow(
                    source_id,
                    "legacy_text",
                    "OBSERVED",
                    f"legacy:{legacy_answers.name}#evidence-row-{line}",
                    contract.sha256_text(legacy_evidence),
                    recorded_at,
                    len(sources) + 2,
                )
            )
            refs.append(f"[evidence:{source_id}]")
        if status == "UNKNOWN":
            source_id = f"legacy-needed-q{question.question_id}"
            sources.append(
                contract.SourceRow(
                    source_id,
                    "expected_measurement",
                    "MISSING",
                    f"legacy-unspecified:q{question.question_id}",
                    "",
                    "",
                    len(sources) + 2,
                )
            )
            refs.append(f"[needed:{source_id}]")
        if status in {"DERIVED", "PENDING_CONTEXT"} and depends_on:
            refs.append(f"[decision:{depends_on}]")
        evidence = " ".join(refs)
        if status == "UNASSESSED":
            answer, evidence, review = "", "", "NOT_REQUIRED"
            migration_state = "MIGRATED"
        elif status in contract.ACCEPTED_STATUSES:
            review = "UNREVIEWED"
            migration_state = "SEMANTIC_REVIEW_REQUIRED"
        else:
            review = "NOT_REQUIRED"
            migration_state = "OPEN_STATUS_REVIEW_REQUIRED"
        answers.append(
            contract.AnswerRow(
                question.question_id,
                status,
                answer,
                evidence,
                depends_on,
                review,
                line,
            )
        )
        report_rows.append((str(question.question_id), status, migration_state))

    events: list[dict] = []
    previous_hash = contract.GENESIS_HASH
    for question, answer in zip(questions, answers):
        event = contract.build_history_event(
            sequence=len(events) + 1,
            recorded_at=recorded_at,
            actor=actor,
            action="BASELINE",
            question=question,
            state=contract.answer_state(answer),
            previous_event_hash=previous_hash,
        )
        events.append(event)
        previous_hash = event["event_hash"]

    validation = contract.validate_rows(questions, answers, sources, events)
    out_dir.mkdir(parents=True, exist_ok=True)
    _atomic_text(
        out_dir / "question-index.tsv",
        _tsv_text(
            contract.QUESTION_HEADER,
            [(str(row.question_id), row.question, row.question_fingerprint) for row in questions],
        ),
    )
    _atomic_text(
        out_dir / "answer-register.csv",
        _csv_text(
            contract.ANSWER_HEADER,
            [tuple(str(getattr(row, field)) for field in contract.ANSWER_HEADER) for row in answers],
        ),
    )
    _atomic_text(
        out_dir / "source-manifest.csv",
        _csv_text(
            contract.SOURCE_HEADER,
            [tuple(str(getattr(row, field)) for field in contract.SOURCE_HEADER) for row in sources],
        ),
    )
    _atomic_text(out_dir / "decision-history.jsonl", _history_text(events))
    _atomic_text(
        out_dir / "migration-report.tsv",
        _tsv_text(("question_id", "legacy_status", "migration_state"), report_rows),
    )
    return validation


def _load_contract(paths: tuple[Path, Path, Path, Path]):
    questions, q_errors = contract.load_questions(paths[0])
    answers, a_errors = contract.load_answers(paths[1])
    sources, s_errors = contract.load_sources(paths[2])
    history, h_errors = contract.load_history(paths[3])
    report = contract.validate_rows(
        questions,
        answers,
        sources,
        history,
        initial_errors=q_errors + a_errors + s_errors + h_errors,
    )
    if report.errors:
        raise ValueError("текущий реестр невалиден: " + " | ".join(report.errors[:5]))
    return questions, answers, sources, history


def _write_answers(path: Path, answers: list[contract.AnswerRow]) -> None:
    _atomic_text(
        path,
        _csv_text(
            contract.ANSWER_HEADER,
            [tuple(str(getattr(row, field)) for field in contract.ANSWER_HEADER) for row in answers],
        ),
    )


def change_row(
    paths: tuple[Path, Path, Path, Path],
    *,
    question_id: int,
    status: str,
    answer: str,
    evidence: str,
    depends_on: str,
    actor: str,
    recorded_at: str,
) -> contract.ValidationReport:
    _require_absolute(list(paths))
    questions, answers, sources, history = _load_contract(paths)
    question_map = {row.question_id: row for row in questions}
    if question_id not in question_map:
        raise ValueError(f"нет question_id {question_id}")
    review = "UNREVIEWED" if status in contract.ACCEPTED_STATUSES else "NOT_REQUIRED"
    replacement = contract.AnswerRow(question_id, status, answer, evidence, depends_on, review, 0)
    new_answers = [replacement if row.question_id == question_id else row for row in answers]
    previous_hash = history[-1]["event_hash"]
    event = contract.build_history_event(
        sequence=len(history) + 1,
        recorded_at=recorded_at,
        actor=actor,
        action="UPDATE",
        question=question_map[question_id],
        state=contract.answer_state(replacement),
        previous_event_hash=previous_hash,
    )
    new_history = [{key: value for key, value in item.items() if key != "_line"} for item in history] + [event]
    validation = contract.validate_rows(questions, new_answers, sources, new_history)
    if validation.errors:
        raise ValueError("изменение отклонено: " + " | ".join(validation.errors[:5]))
    _write_answers(paths[1], new_answers)
    _atomic_text(paths[3], _history_text(new_history))
    return validation


def review_row(
    paths: tuple[Path, Path, Path, Path],
    *,
    question_id: int,
    reviewer: str,
    basis: str,
    recorded_at: str,
) -> contract.ValidationReport:
    _require_absolute(list(paths))
    questions, answers, sources, history = _load_contract(paths)
    question_map = {row.question_id: row for row in questions}
    current = next((row for row in answers if row.question_id == question_id), None)
    if current is None or current.status not in contract.ACCEPTED_STATUSES:
        raise ValueError("semantic review допустим только для ANSWERED или DERIVED")
    if current.semantic_review != "UNREVIEWED":
        raise ValueError("строка не находится в UNREVIEWED")
    replacement = contract.AnswerRow(
        current.question_id,
        current.status,
        current.answer,
        current.evidence,
        current.depends_on,
        "REVIEWED",
        current.line,
    )
    new_answers = [replacement if row.question_id == question_id else row for row in answers]
    event = contract.build_history_event(
        sequence=len(history) + 1,
        recorded_at=recorded_at,
        actor=reviewer,
        action="SEMANTIC_REVIEW",
        question=question_map[question_id],
        state=contract.answer_state(replacement),
        previous_event_hash=history[-1]["event_hash"],
        review_basis=basis,
    )
    new_history = [{key: value for key, value in item.items() if key != "_line"} for item in history] + [event]
    validation = contract.validate_rows(questions, new_answers, sources, new_history)
    if validation.errors:
        raise ValueError("review отклонён: " + " | ".join(validation.errors[:5]))
    _write_answers(paths[1], new_answers)
    _atomic_text(paths[3], _history_text(new_history))
    return validation


def _contract_paths(args) -> tuple[Path, Path, Path, Path]:
    return args.questions, args.answers, args.sources, args.history


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    migrate = subparsers.add_parser("migrate")
    migrate.add_argument("--legacy-questions", required=True, type=Path)
    migrate.add_argument("--legacy-answers", required=True, type=Path)
    migrate.add_argument("--out-dir", required=True, type=Path)
    migrate.add_argument("--actor", required=True)
    migrate.add_argument("--recorded-at", required=True)

    for name in ("update", "review"):
        command = subparsers.add_parser(name)
        command.add_argument("--questions", required=True, type=Path)
        command.add_argument("--answers", required=True, type=Path)
        command.add_argument("--sources", required=True, type=Path)
        command.add_argument("--history", required=True, type=Path)
        command.add_argument("--question-id", required=True, type=int)
        command.add_argument("--recorded-at", required=True)
    update = subparsers.choices["update"]
    update.add_argument("--status", required=True)
    update.add_argument("--answer", required=True)
    update.add_argument("--evidence", required=True)
    update.add_argument("--depends-on", default="")
    update.add_argument("--actor", required=True)
    review = subparsers.choices["review"]
    review.add_argument("--reviewer", required=True)
    review.add_argument("--basis", required=True)
    args = parser.parse_args(argv)

    try:
        if args.command == "migrate":
            report = migrate_legacy(
                args.legacy_questions,
                args.legacy_answers,
                args.out_dir,
                actor=args.actor,
                recorded_at=args.recorded_at,
            )
        elif args.command == "update":
            report = change_row(
                _contract_paths(args),
                question_id=args.question_id,
                status=args.status,
                answer=args.answer,
                evidence=args.evidence,
                depends_on=args.depends_on,
                actor=args.actor,
                recorded_at=args.recorded_at,
            )
        else:
            report = review_row(
                _contract_paths(args),
                question_id=args.question_id,
                reviewer=args.reviewer,
                basis=args.basis,
                recorded_at=args.recorded_at,
            )
    except (OSError, ValueError) as error:
        print(f"ОШИБКА: {error}", file=sys.stderr)
        return 1
    if report.errors:
        for error in report.errors:
            print(f"ОШИБКА: {error}", file=sys.stderr)
        return 1
    print("Операция завершена; hash-chain и текущий снимок согласованы.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
