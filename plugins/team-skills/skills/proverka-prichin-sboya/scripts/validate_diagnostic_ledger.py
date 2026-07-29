#!/usr/bin/env python3
"""Проверяет структуру JSONL-журнала различающих диагностических опытов."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = (
    "outcome",
    "observed_facts",
    "state_fingerprint",
    "causal_boundaries",
    "hypothesis_a",
    "hypothesis_b",
    "causal_contrast",
    "held_constant",
    "probe",
    "owner",
    "expected_if_a",
    "expected_if_b",
    "evidence_to_capture",
    "safety_gate",
    "stop_condition",
    "verdict",
)

ALLOWED_VERDICTS = {
    "outcome_reached",
    "favors_a",
    "favors_b",
    "inconclusive",
    "invalid_test",
    "blocked",
}

ALLOWED_OWNERS = {"assistant", "user", "both"}

STRING_FIELDS = (
    "outcome",
    "hypothesis_a",
    "hypothesis_b",
    "causal_contrast",
    "probe",
    "expected_if_a",
    "expected_if_b",
    "evidence_to_capture",
    "safety_gate",
    "stop_condition",
)

STRING_LIST_FIELDS = ("causal_boundaries", "held_constant")
OBSERVED_FACT_FIELDS = ("fact", "source", "observed_at")

NON_CAUSAL_FINGERPRINT_FIELDS = {
    "observed_at",
    "timestamp",
    "time",
    "captured_at",
    "collected_at",
    "recorded_at",
    "last_checked_at",
}


def _is_nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


def _normalized_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def _stable_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _causal_fingerprint(value: Any) -> Any:
    """Удалить служебное время, сохранив причинно значимые поля."""

    if isinstance(value, dict):
        return {
            key: _causal_fingerprint(item)
            for key, item in value.items()
            if not (
                isinstance(key, str)
                and key.casefold() in NON_CAUSAL_FINGERPRINT_FIELDS
            )
        }
    if isinstance(value, list):
        return [_causal_fingerprint(item) for item in value]
    return value


def _validate_field_types(entry: dict[str, Any], *, label: str) -> list[str]:
    errors: list[str] = []

    for field in STRING_FIELDS:
        value = entry.get(field)
        if _is_nonempty(value) and not isinstance(value, str):
            errors.append(f"{label}: поле {field} должно быть непустой строкой")

    for field in STRING_LIST_FIELDS:
        value = entry.get(field)
        if not _is_nonempty(value):
            continue
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item.strip() for item in value
        ):
            errors.append(f"{label}: поле {field} должно быть непустым списком строк")

    fingerprint = entry.get("state_fingerprint")
    if _is_nonempty(fingerprint) and not isinstance(fingerprint, dict):
        errors.append(f"{label}: поле state_fingerprint должно быть непустым object")

    observed_facts = entry.get("observed_facts")
    if _is_nonempty(observed_facts):
        if not isinstance(observed_facts, list):
            errors.append(f"{label}: поле observed_facts должно быть непустым списком object")
        else:
            for fact_index, fact in enumerate(observed_facts, start=1):
                fact_label = f"{label}.observed_facts[{fact_index}]"
                if not isinstance(fact, dict):
                    errors.append(f"{fact_label}: ожидается object")
                    continue
                invalid = [
                    field
                    for field in OBSERVED_FACT_FIELDS
                    if not isinstance(fact.get(field), str) or not fact[field].strip()
                ]
                if invalid:
                    errors.append(
                        f"{fact_label}: нужны непустые строки: {', '.join(invalid)}"
                    )

    return errors


def validate_entries(entries: list[Any]) -> list[str]:
    """Вернуть список структурных ошибок без проверки причинной корректности."""

    errors: list[str] = []
    seen_probes: dict[tuple[str, str], int] = {}

    for index, entry in enumerate(entries, start=1):
        label = f"запись {index}"
        if not isinstance(entry, dict):
            errors.append(f"{label}: ожидается JSON object")
            continue

        missing = [field for field in REQUIRED_FIELDS if not _is_nonempty(entry.get(field))]
        if missing:
            errors.append(f"{label}: отсутствуют обязательные поля: {', '.join(missing)}")

        errors.extend(_validate_field_types(entry, label=label))

        verdict = entry.get("verdict")
        if _is_nonempty(verdict) and (
            not isinstance(verdict, str) or verdict not in ALLOWED_VERDICTS
        ):
            errors.append(
                f"{label}: неизвестный verdict {verdict!r}; допустимы: "
                + ", ".join(sorted(ALLOWED_VERDICTS))
            )

        owner = entry.get("owner")
        if _is_nonempty(owner) and (
            not isinstance(owner, str) or owner not in ALLOWED_OWNERS
        ):
            errors.append(
                f"{label}: неизвестный owner {owner!r}; допустимы: "
                + ", ".join(sorted(ALLOWED_OWNERS))
            )

        hypothesis_a = entry.get("hypothesis_a")
        hypothesis_b = entry.get("hypothesis_b")
        if isinstance(hypothesis_a, str) and isinstance(hypothesis_b, str):
            if _normalized_text(hypothesis_a) == _normalized_text(hypothesis_b):
                errors.append(f"{label}: hypothesis_a и hypothesis_b не различаются")

        expected_if_a = entry.get("expected_if_a")
        expected_if_b = entry.get("expected_if_b")
        if isinstance(expected_if_a, str) and isinstance(expected_if_b, str):
            if _normalized_text(expected_if_a) == _normalized_text(expected_if_b):
                errors.append(f"{label}: expected_if_a и expected_if_b не различаются")

        fingerprint = entry.get("state_fingerprint")
        probe = entry.get("probe")
        if isinstance(fingerprint, dict) and isinstance(probe, str) and probe.strip():
            key = (
                _stable_key(_causal_fingerprint(fingerprint)),
                _normalized_text(probe),
            )
            previous = seen_probes.get(key)
            if previous is not None:
                errors.append(
                    f"{label}: дублирует probe записи {previous} при том же state_fingerprint"
                )
            else:
                seen_probes[key] = index

    return errors


def load_jsonl(path: Path) -> tuple[list[Any], list[str]]:
    entries: list[Any] = []
    errors: list[str] = []

    if not path.is_file():
        return entries, [f"файл не найден: {path}"]

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        return entries, [f"не удалось прочитать журнал: {error}"]

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as error:
            errors.append(
                f"строка {line_number}: некорректный JSON "
                f"(столбец {error.colno}: {error.msg})"
            )

    if not entries and not errors:
        errors.append("журнал не содержит ни одной записи")

    return entries, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path, help="Путь к experiment-ledger.jsonl")
    args = parser.parse_args(argv)

    entries, errors = load_jsonl(args.ledger)
    errors.extend(validate_entries(entries))

    if errors:
        for error in errors:
            print(f"ОШИБКА: {error}", file=sys.stderr)
        return 1

    print(f"Журнал диагностики структурно корректен: записей {len(entries)}.")
    print("Причинная независимость гипотез требует отдельной смысловой проверки.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
