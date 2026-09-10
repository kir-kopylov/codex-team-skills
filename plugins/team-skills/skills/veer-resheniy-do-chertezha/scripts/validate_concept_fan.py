#!/usr/bin/env python3
"""Проверяет структурные gates веера физических концепций."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


MIN_CONCEPTS = 5
MAX_CONCEPTS = 7

TEXT_FIELDS = (
    "id",
    "name",
    "target_action",
    "user_value",
    "mechanism",
    "difference_rationale",
    "use_conditions",
    "batch_assumption",
)

ENUM_FIELDS = {
    "primary_material_family": {
        "cellulose",
        "wood",
        "metal",
        "rigid_polymer",
        "elastomer",
        "textile",
        "glass",
        "ceramic",
        "mineral_composite",
        "bio_material",
    },
    "primary_fabrication_process": {
        "fold_score",
        "laser_cut",
        "sheet_bend",
        "machining",
        "casting",
        "sewing",
        "additive_manufacturing",
        "lamination",
        "mechanical_assembly",
        "print_coat",
    },
    "primary_physical_behavior": {
        "rigid",
        "elastic",
        "weighted_stable",
        "foldable_transformable",
        "articulated_rotating",
        "magnetic_reconfigurable",
        "optical_dynamic",
        "soft_tactile",
    },
    "interaction_mode": {
        "observe",
        "rotate",
        "unfold",
        "press",
        "rearrange",
        "assemble",
        "touch",
        "trigger",
    },
}

COVERAGE_AXES = tuple(ENUM_FIELDS)
CONSTRAINT_KINDS = {"hard", "soft", "unknown"}
CONSTRAINT_STATUSES = {"pass", "unknown", "fail"}
CONFIDENCE_LEVELS = {"low", "medium", "high"}
PRODUCTION_COMPLEXITIES = {"low", "medium", "high"}
RELATIVE_COSTS = {"low", "medium", "high", "unknown"}
SEMANTIC_AXES = {
    "material_family",
    "fabrication_process",
    "physical_behavior",
    "interaction_mode",
    "mechanism",
    "constraints",
    "shortlist",
}


def normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def is_text(value: Any) -> bool:
    return type(value) is str and bool(value.strip())


def validate_text(mapping: dict[str, Any], key: str, path: str, errors: list[str]) -> None:
    if not is_text(mapping.get(key)):
        errors.append(f"{path}.{key} должен быть непустой строкой.")


def validate_string_list(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, list) or not value:
        errors.append(f"{path} должен быть непустым списком строк.")
        return
    for index, item in enumerate(value):
        if not is_text(item):
            errors.append(f"{path}[{index}] должен быть непустой строкой.")


def validate_constraints(value: Any, errors: list[str]) -> dict[str, str]:
    if not isinstance(value, list) or not value:
        errors.append("constraints должен быть непустым списком.")
        return {}

    constraints: dict[str, str] = {}
    for index, item in enumerate(value):
        path = f"constraints[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path} должен быть объектом.")
            continue
        for key in ("id", "statement", "source"):
            validate_text(item, key, path, errors)
        kind = item.get("kind")
        if kind not in CONSTRAINT_KINDS:
            errors.append(f"{path}.kind должен быть одним из {sorted(CONSTRAINT_KINDS)}.")
        constraint_id = item.get("id")
        if is_text(constraint_id):
            normalized = normalize(constraint_id)
            if normalized in constraints:
                errors.append(f"Дублируется constraint id: {constraint_id}.")
            elif kind in CONSTRAINT_KINDS:
                constraints[normalized] = kind
    return constraints


def validate_criteria(value: Any, errors: list[str]) -> dict[str, int]:
    if not isinstance(value, list) or not 3 <= len(value) <= 7:
        errors.append("decision_criteria должен содержать 3–7 критериев.")
        return {}

    criteria: dict[str, int] = {}
    for index, item in enumerate(value):
        path = f"decision_criteria[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path} должен быть объектом.")
            continue
        validate_text(item, "id", path, errors)
        validate_text(item, "name", path, errors)
        weight = item.get("weight")
        if type(weight) is not int or not 1 <= weight <= 5:
            errors.append(f"{path}.weight должен быть целым числом от 1 до 5.")
        criterion_id = item.get("id")
        if is_text(criterion_id):
            normalized = normalize(criterion_id)
            if normalized in criteria:
                errors.append(f"Дублируется criterion id: {criterion_id}.")
            elif type(weight) is int and 1 <= weight <= 5:
                criteria[normalized] = weight
    if "outcome_fit" not in criteria:
        errors.append("decision_criteria должен содержать обязательный id outcome_fit.")
    return criteria


def validate_coverage_targets(value: Any, concept_count: int, errors: list[str]) -> dict[str, int]:
    if not isinstance(value, dict):
        errors.append("coverage_targets должен быть объектом.")
        return {}

    targets: dict[str, int] = {}
    for axis in COVERAGE_AXES:
        target = value.get(axis)
        if type(target) is not int or not 1 <= target <= max(concept_count, 1):
            errors.append(
                f"coverage_targets.{axis} должен быть целым числом от 1 до количества концепций."
            )
        else:
            targets[axis] = target
    return targets


def validate_constraint_results(
    value: Any,
    concept_path: str,
    constraints: dict[str, str],
    errors: list[str],
) -> dict[str, str]:
    if not isinstance(value, list):
        errors.append(f"{concept_path}.constraint_results должен быть списком.")
        return {}

    results: dict[str, str] = {}
    for index, item in enumerate(value):
        path = f"{concept_path}.constraint_results[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path} должен быть объектом.")
            continue
        validate_text(item, "constraint_id", path, errors)
        validate_text(item, "evidence", path, errors)
        status = item.get("status")
        if status not in CONSTRAINT_STATUSES:
            errors.append(f"{path}.status должен быть одним из {sorted(CONSTRAINT_STATUSES)}.")
        constraint_id = item.get("constraint_id")
        if is_text(constraint_id):
            normalized = normalize(constraint_id)
            if normalized not in constraints:
                errors.append(f"{path} ссылается на неизвестный constraint id: {constraint_id}.")
            elif normalized in results:
                errors.append(f"{concept_path} повторяет constraint id: {constraint_id}.")
            elif status in CONSTRAINT_STATUSES:
                results[normalized] = status
                if status == "fail":
                    errors.append(f"{concept_path} не прошёл constraint {constraint_id} и должен быть удалён.")

    missing = sorted(set(constraints) - set(results))
    if missing:
        errors.append(f"{concept_path} не проверил constraints: {', '.join(missing)}.")
    return results


def validate_criterion_scores(
    value: Any,
    concept_path: str,
    criteria: dict[str, int],
    errors: list[str],
) -> dict[str, int]:
    if not isinstance(value, list):
        errors.append(f"{concept_path}.criterion_scores должен быть списком.")
        return {}

    scores: dict[str, int] = {}
    for index, item in enumerate(value):
        path = f"{concept_path}.criterion_scores[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path} должен быть объектом.")
            continue
        validate_text(item, "criterion_id", path, errors)
        validate_text(item, "evidence", path, errors)
        score = item.get("score")
        if type(score) is not int or not 1 <= score <= 5:
            errors.append(f"{path}.score должен быть целым числом от 1 до 5.")
        confidence = item.get("confidence")
        if confidence not in CONFIDENCE_LEVELS:
            errors.append(f"{path}.confidence должен быть одним из {sorted(CONFIDENCE_LEVELS)}.")
        criterion_id = item.get("criterion_id")
        if is_text(criterion_id):
            normalized = normalize(criterion_id)
            if normalized not in criteria:
                errors.append(f"{path} ссылается на неизвестный criterion id: {criterion_id}.")
            elif normalized in scores:
                errors.append(f"{concept_path} повторяет criterion id: {criterion_id}.")
            elif type(score) is int and 1 <= score <= 5:
                scores[normalized] = score

    missing = sorted(set(criteria) - set(scores))
    if missing:
        errors.append(f"{concept_path} не оценил criteria: {', '.join(missing)}.")
    return scores


def validate_prototype_check(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{path} должен быть объектом.")
        return
    for key in ("hypothesis", "observable", "failure_condition"):
        validate_text(value, key, path, errors)


def hard_constraints_pass(results: dict[str, str], constraints: dict[str, str]) -> bool:
    hard_ids = {constraint_id for constraint_id, kind in constraints.items() if kind == "hard"}
    return all(results.get(constraint_id) == "pass" for constraint_id in hard_ids)


def dominates(first: dict[str, int], second: dict[str, int], criteria: set[str]) -> bool:
    if not criteria <= set(first) or not criteria <= set(second):
        return False
    return all(first[key] >= second[key] for key in criteria) and any(
        first[key] > second[key] for key in criteria
    )


def weighted_score(scores: dict[str, int], criteria: dict[str, int]) -> int | None:
    if not set(criteria) <= set(scores):
        return None
    return sum(scores[criterion_id] * weight for criterion_id, weight in criteria.items())


def validate_semantic_review(value: Any, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("semantic_review должен быть объектом.")
        return
    if value.get("status") != "pass":
        errors.append("semantic_review.status должен быть pass.")
    if value.get("performed_by") not in {"assistant", "user", "expert"}:
        errors.append("semantic_review.performed_by должен быть assistant, user или expert.")
    validate_text(value, "notes", "semantic_review", errors)
    axes = value.get("reviewed_axes")
    validate_string_list(axes, "semantic_review.reviewed_axes", errors)
    if isinstance(axes, list) and all(is_text(item) for item in axes):
        missing = sorted(SEMANTIC_AXES - {normalize(item) for item in axes})
        if missing:
            errors.append("semantic_review не покрыл оси: " + ", ".join(missing) + ".")


def validate_document(document: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(document, dict):
        return ["Корень JSON должен быть объектом."]

    if not is_text(document.get("target_action")):
        errors.append("target_action должен быть непустой строкой.")

    constraints = validate_constraints(document.get("constraints"), errors)
    criteria = validate_criteria(document.get("decision_criteria"), errors)

    concepts = document.get("concepts")
    if not isinstance(concepts, list):
        errors.append("concepts должен быть списком.")
        concepts = []
    elif not MIN_CONCEPTS <= len(concepts) <= MAX_CONCEPTS:
        errors.append(f"Нужно {MIN_CONCEPTS}–{MAX_CONCEPTS} концепций, получено: {len(concepts)}.")

    coverage_targets = validate_coverage_targets(document.get("coverage_targets"), len(concepts), errors)
    coverage_values: dict[str, set[str]] = {axis: set() for axis in COVERAGE_AXES}
    concept_by_id: dict[str, dict[str, Any]] = {}
    constraint_results_by_id: dict[str, dict[str, str]] = {}
    scores_by_id: dict[str, dict[str, int]] = {}
    signatures: set[tuple[str, ...]] = set()

    for index, concept in enumerate(concepts):
        path = f"concepts[{index}]"
        if not isinstance(concept, dict):
            errors.append(f"{path} должен быть объектом.")
            continue

        for field in TEXT_FIELDS:
            validate_text(concept, field, path, errors)
        for field, allowed in ENUM_FIELDS.items():
            value = concept.get(field)
            if value not in allowed:
                errors.append(f"{path}.{field} должен быть одним из {sorted(allowed)}.")
            else:
                coverage_values[field].add(value)

        if concept.get("production_complexity") not in PRODUCTION_COMPLEXITIES:
            errors.append(
                f"{path}.production_complexity должен быть одним из {sorted(PRODUCTION_COMPLEXITIES)}."
            )
        if concept.get("relative_cost") not in RELATIVE_COSTS:
            errors.append(f"{path}.relative_cost должен быть одним из {sorted(RELATIVE_COSTS)}.")
        if concept.get("cost_confidence") not in CONFIDENCE_LEVELS:
            errors.append(f"{path}.cost_confidence должен быть одним из {sorted(CONFIDENCE_LEVELS)}.")
        validate_string_list(concept.get("cost_drivers"), f"{path}.cost_drivers", errors)
        validate_string_list(concept.get("risks"), f"{path}.risks", errors)
        validate_prototype_check(concept.get("prototype_check"), f"{path}.prototype_check", errors)

        results = validate_constraint_results(concept.get("constraint_results"), path, constraints, errors)
        scores = validate_criterion_scores(concept.get("criterion_scores"), path, criteria, errors)

        concept_id = concept.get("id")
        if is_text(concept_id):
            normalized_id = normalize(concept_id)
            if normalized_id in concept_by_id:
                errors.append(f"Дублируется concept id: {concept_id}.")
            else:
                concept_by_id[normalized_id] = concept
                constraint_results_by_id[normalized_id] = results
                scores_by_id[normalized_id] = scores

        signature_values = [
            concept.get("primary_material_family"),
            concept.get("primary_fabrication_process"),
            concept.get("primary_physical_behavior"),
            concept.get("interaction_mode"),
            concept.get("mechanism"),
            concept.get("user_value"),
        ]
        if all(is_text(value) for value in signature_values):
            signature = tuple(normalize(value) for value in signature_values)
            if signature in signatures:
                errors.append(f"{path} дублирует полный concept signature.")
            signatures.add(signature)

    for axis, target in coverage_targets.items():
        actual = len(coverage_values[axis])
        if actual < target:
            errors.append(f"Coverage {axis}: нужно {target}, получено {actual}.")

    shortlist = document.get("shortlist")
    shortlisted_ids: list[str] = []
    if not isinstance(shortlist, list) or not 2 <= len(shortlist) <= 3:
        errors.append("shortlist должен содержать 2–3 объекта.")
    else:
        for index, item in enumerate(shortlist):
            path = f"shortlist[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{path} должен быть объектом.")
                continue
            for key in ("id", "decision_reason", "next_test"):
                validate_text(item, key, path, errors)
            concept_id = item.get("id")
            if not is_text(concept_id):
                continue
            normalized_id = normalize(concept_id)
            if normalized_id in shortlisted_ids:
                errors.append(f"shortlist повторяет id: {concept_id}.")
                continue
            shortlisted_ids.append(normalized_id)
            if normalized_id not in concept_by_id:
                errors.append(f"shortlist ссылается на неизвестный id: {concept_id}.")
                continue
            if not hard_constraints_pass(constraint_results_by_id[normalized_id], constraints):
                errors.append(f"shortlist содержит {concept_id} без pass по всем hard constraints.")

    eligible_ids = [
        concept_id
        for concept_id in concept_by_id
        if hard_constraints_pass(constraint_results_by_id[concept_id], constraints)
    ]
    criteria_ids = set(criteria)
    for shortlisted_id in shortlisted_ids:
        if shortlisted_id not in concept_by_id or shortlisted_id not in eligible_ids:
            continue
        dominators = [
            candidate_id
            for candidate_id in eligible_ids
            if candidate_id != shortlisted_id
            and dominates(scores_by_id[candidate_id], scores_by_id[shortlisted_id], criteria_ids)
        ]
        if dominators:
            errors.append(
                f"Shortlist concept {shortlisted_id} доминируется: {', '.join(sorted(dominators))}."
            )

    eligible_weighted_scores = {
        concept_id: score
        for concept_id in eligible_ids
        if (score := weighted_score(scores_by_id[concept_id], criteria)) is not None
    }
    if eligible_weighted_scores:
        best_score = max(eligible_weighted_scores.values())
        best_ids = {
            concept_id
            for concept_id, score in eligible_weighted_scores.items()
            if score == best_score
        }
        if not best_ids.intersection(shortlisted_ids):
            errors.append(
                "shortlist должен содержать хотя бы один concept с максимальным weighted score: "
                + ", ".join(sorted(best_ids))
                + "."
            )

    validate_semantic_review(document.get("semantic_review"), errors)
    return errors


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_file", type=Path, help="JSON-файл с веером концепций")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        document = json.loads(args.json_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"FAIL\nФайл не найден: {args.json_file}", file=sys.stderr)
        return 2
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"FAIL\nНе удалось прочитать JSON: {exc}", file=sys.stderr)
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
