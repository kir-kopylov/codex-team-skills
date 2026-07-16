#!/usr/bin/env python3
"""Проверяет минимальную структуру и разнообразие веера физических концепций."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = (
    "id",
    "name",
    "target_action",
    "mechanism",
    "primary_material_class",
    "primary_technology",
    "primary_physical_behavior",
    "interaction",
    "use_conditions",
    "production_complexity",
    "cost_class",
    "risks",
    "prototype_check",
)

UNIQUE_FIELDS = (
    "mechanism",
    "primary_material_class",
    "primary_technology",
    "primary_physical_behavior",
)


def normalize(value: Any) -> str:
    return " ".join(str(value).casefold().split())


def is_nonempty(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value) and all(isinstance(item, str) and item.strip() for item in value)
    return value is not None


def validate_document(document: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(document, dict):
        return ["Корень JSON должен быть объектом."]

    concepts = document.get("concepts")
    if not isinstance(concepts, list):
        return ["Поле concepts должно быть списком."]
    if len(concepts) < 5:
        errors.append(f"Нужно минимум 5 концепций, получено: {len(concepts)}.")

    ids: list[str] = []
    for index, concept in enumerate(concepts, start=1):
        label = f"concepts[{index - 1}]"
        if not isinstance(concept, dict):
            errors.append(f"{label} должен быть объектом.")
            continue
        for field in REQUIRED_FIELDS:
            if field not in concept or not is_nonempty(concept[field]):
                errors.append(f"{label}.{field} отсутствует или пусто.")
        concept_id = concept.get("id")
        if isinstance(concept_id, str) and concept_id.strip():
            ids.append(normalize(concept_id))

    if len(ids) != len(set(ids)):
        errors.append("Идентификаторы концепций должны быть уникальными.")

    for field in UNIQUE_FIELDS:
        values = [
            normalize(concept.get(field))
            for concept in concepts
            if isinstance(concept, dict) and is_nonempty(concept.get(field))
        ]
        if len(values) != len(set(values)):
            errors.append(f"Поле {field} должно быть уникальным у каждой концепции.")

    shortlist = document.get("shortlist")
    if not isinstance(shortlist, list) or not 2 <= len(shortlist) <= 3:
        errors.append("Поле shortlist должно содержать 2–3 идентификатора концепций.")
    else:
        normalized_shortlist = [normalize(item) for item in shortlist]
        if any(not item for item in normalized_shortlist):
            errors.append("shortlist содержит пустой идентификатор.")
        if len(normalized_shortlist) != len(set(normalized_shortlist)):
            errors.append("shortlist не должен содержать повторы.")
        unknown = sorted(set(normalized_shortlist) - set(ids))
        if unknown:
            errors.append("shortlist ссылается на неизвестные id: " + ", ".join(unknown) + ".")

    return errors


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_file", type=Path, help="JSON-файл с concepts и shortlist")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        document = json.loads(args.json_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"FAIL\nФайл не найден: {args.json_file}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"FAIL\nНекорректный JSON: {exc}", file=sys.stderr)
        return 2

    errors = validate_document(document)
    if errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
