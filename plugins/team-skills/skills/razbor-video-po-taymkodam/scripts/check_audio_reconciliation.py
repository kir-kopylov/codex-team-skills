#!/usr/bin/env python3
"""Проверка покрытия, учёта черновика и формата стенограммы."""

import argparse
import json
from pathlib import Path
import re
import sys


NOTES_HEADING = "Примечания редактора"
REPLICA = re.compile(r"\[([0-9]{2}):([0-5][0-9]):([0-5][0-9])\] ([^:\s][^:]*): (\S.*)")


def read_utterances(transcript, duration_ms):
    lines = [line for line in transcript.splitlines() if line.strip()]
    if lines.count(NOTES_HEADING) != 1:
        raise ValueError("Нужен один раздел «Примечания редактора».")
    boundary = lines.index(NOTES_HEADING)
    if boundary == len(lines) - 1:
        raise ValueError("Примечания редактора пусты.")
    if any(REPLICA.fullmatch(line) for line in lines[boundary + 1:]):
        raise ValueError("Реплики должны предшествовать примечаниям редактора.")

    previous = -1
    for number, line in enumerate(lines[:boundary], 1):
        match = REPLICA.fullmatch(line)
        if not match:
            raise ValueError(f"Неверный формат реплики {number}.")
        hours, minutes, seconds = map(int, match.groups()[:3])
        position = (hours * 3600 + minutes * 60 + seconds) * 1000
        if position >= duration_ms or position < previous:
            raise ValueError(f"Таймкод реплики {number} вне записи или не по порядку.")
        previous = position
    return boundary


def unchecked_intervals(intervals, duration_ms):
    if not isinstance(intervals, list):
        raise ValueError("Интервалы должны быть списком.")
    spans = []
    for item in intervals:
        if not isinstance(item, dict):
            raise ValueError("Каждый интервал должен быть объектом.")
        start, end = item.get("start_ms"), item.get("end_ms")
        state, basis = item.get("state"), item.get("basis")
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= duration_ms:
            raise ValueError("Границы интервала должны быть целыми миллисекундами в пределах записи.")
        if state not in ("checked", "unclear", "unverified") or not isinstance(basis, str) or not basis.strip():
            raise ValueError("Каждому интервалу нужны допустимое состояние и непустое основание.")
        spans.append((start, end, state))

    gaps = []
    cursor = 0
    for start, end, state in sorted(spans):
        if start < cursor:
            raise ValueError("Интервалы журнала перекрываются.")
        if start > cursor:
            gaps.append([cursor, start])
        if state == "unverified":
            gaps.append([start, end])
        cursor = end
    if cursor < duration_ms:
        gaps.append([cursor, duration_ms])

    combined = []
    for start, end in gaps:
        if combined and start == combined[-1][1]:
            combined[-1][1] = end
        else:
            combined.append([start, end])
    return combined


def unchecked_fragments(fragment_ids, decisions, utterance_count):
    if not isinstance(fragment_ids, list) or any(
        not isinstance(value, str) or not value.strip() for value in fragment_ids
    ):
        raise ValueError("Нужен список непустых идентификаторов черновика.")
    pending = set(fragment_ids)
    if len(pending) != len(fragment_ids):
        raise ValueError("Идентификаторы исходных фрагментов повторяются.")
    if not isinstance(decisions, list):
        raise ValueError("Решения по фрагментам должны быть списком.")

    unverified = []
    for item in decisions:
        if not isinstance(item, dict):
            raise ValueError("Решение по фрагменту должно быть объектом.")
        fragment_id = item.get("id")
        if not isinstance(fragment_id, str) or fragment_id not in pending:
            raise ValueError(f"Неизвестный или повторный фрагмент: {fragment_id!r}.")
        pending.remove(fragment_id)
        fields = set(item) - {"id"}
        if fields == {"lines"}:
            lines = item["lines"]
            if not isinstance(lines, list) or not lines or any(
                type(line) is not int or not 1 <= line <= utterance_count for line in lines
            ) or len(set(lines)) != len(lines):
                raise ValueError(f"Некорректные номера реплик для фрагмента {fragment_id!r}.")
        elif fields in ({"omitted"}, {"unverified"}):
            field, = fields
            reason = item[field]
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError(f"Нужно основание решения по фрагменту {fragment_id!r}.")
            if field == "unverified":
                unverified.append(fragment_id)
        else:
            raise ValueError(f"У фрагмента {fragment_id!r} должно быть ровно одно решение.")
    if pending:
        missing = ", ".join(sorted(pending))
        raise ValueError(f"Не учтены фрагменты черновика: {missing}.")
    return unverified


def validate(ledger, transcript):
    if not isinstance(ledger, dict):
        raise ValueError("Журнал сверки должен быть объектом JSON.")
    duration_ms = ledger.get("duration_ms")
    if type(duration_ms) is not int or duration_ms <= 0:
        raise ValueError("Нужна положительная исходная длительность в целых миллисекундах.")
    utterances = read_utterances(transcript, duration_ms)
    intervals = unchecked_intervals(ledger.get("intervals"), duration_ms)
    fragments = unchecked_fragments(ledger.get("draft_ids"), ledger.get("decisions"), utterances)
    return {
        "status": "partial" if intervals or fragments else "complete",
        "duration_ms": duration_ms,
        "utterances": utterances,
        "draft_fragments": len(ledger["draft_ids"]),
        "unverified_intervals_ms": intervals,
        "unverified_fragment_ids": fragments,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True, help="журнал сверки в JSON")
    parser.add_argument("--transcript", type=Path, required=True, help="стенограмма в UTF-8")
    args = parser.parse_args()
    try:
        ledger = json.loads(args.ledger.read_text(encoding="utf-8"))
        report = validate(ledger, args.transcript.read_text(encoding="utf-8"))
    except (ValueError, OSError) as error:
        print(f"Проверка не пройдена. {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
