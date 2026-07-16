from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "plugins" / "team-skills" / "skills" / "physical-solution-diversifier"
SCRIPT = SKILL_DIR / "scripts" / "validate_concept_fan.py"

MATERIALS = ["cellulose", "wood", "metal", "rigid_polymer", "textile", "elastomer"]
PROCESSES = ["fold_score", "laser_cut", "sheet_bend", "additive_manufacturing", "sewing", "casting"]
BEHAVIORS = [
    "foldable_transformable",
    "articulated_rotating",
    "magnetic_reconfigurable",
    "rigid",
    "soft_tactile",
    "elastic",
]
INTERACTIONS = ["unfold", "rotate", "rearrange", "observe", "touch", "press"]
SCORE_SETS = [
    {"outcome_fit": 5, "production_ease": 3, "updateability": 4},
    {"outcome_fit": 4, "production_ease": 5, "updateability": 3},
    {"outcome_fit": 3, "production_ease": 4, "updateability": 5},
    {"outcome_fit": 5, "production_ease": 2, "updateability": 3},
    {"outcome_fit": 4, "production_ease": 4, "updateability": 2},
    {"outcome_fit": 2, "production_ease": 2, "updateability": 2},
]


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_concept_fan", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_concept(index: int) -> dict:
    scores = SCORE_SETS[index % len(SCORE_SETS)]
    return {
        "id": f"c{index + 1}",
        "name": f"Концепция {index + 1}",
        "target_action": f"Действие {index + 1}",
        "user_value": f"Отдельная ценность {index + 1}",
        "mechanism": f"Механизм {index + 1}",
        "primary_material_family": MATERIALS[index % len(MATERIALS)],
        "primary_fabrication_process": PROCESSES[index % len(PROCESSES)],
        "primary_physical_behavior": BEHAVIORS[index % len(BEHAVIORS)],
        "interaction_mode": INTERACTIONS[index % len(INTERACTIONS)],
        "difference_rationale": f"Отличается пользовательским сценарием {index + 1}",
        "use_conditions": "Помещение",
        "production_complexity": "medium",
        "batch_assumption": "20 экземпляров",
        "relative_cost": "medium",
        "cost_confidence": "medium",
        "cost_drivers": ["Материал", "Сборка"],
        "risks": ["Риск прототипа"],
        "constraint_results": [
            {
                "constraint_id": "c_network",
                "status": "pass",
                "evidence": "Механизм не требует сети",
            }
        ],
        "criterion_scores": [
            {
                "criterion_id": criterion_id,
                "score": score,
                "confidence": "medium",
                "evidence": f"Проверяемое предположение для {criterion_id}",
            }
            for criterion_id, score in scores.items()
        ],
        "prototype_check": {
            "hypothesis": "Пользователь понимает механику",
            "observable": "Четыре из пяти участников справились",
            "failure_condition": "Два участника не справились",
        },
    }


def valid_document(concept_count: int = 5) -> dict:
    return {
        "target_action": "Пользователь быстро выбирает подходящее действие",
        "constraints": [
            {
                "id": "c_network",
                "kind": "hard",
                "statement": "Не требует сети",
                "source": "user",
            }
        ],
        "decision_criteria": [
            {"id": "outcome_fit", "name": "Попадание в цель", "weight": 5},
            {"id": "production_ease", "name": "Простота изготовления", "weight": 3},
            {"id": "updateability", "name": "Обновляемость", "weight": 2},
        ],
        "coverage_targets": {
            "primary_material_family": min(4, concept_count),
            "primary_fabrication_process": min(4, concept_count),
            "primary_physical_behavior": min(4, concept_count),
            "interaction_mode": min(4, concept_count),
        },
        "concepts": [make_concept(index) for index in range(concept_count)],
        "shortlist": [
            {"id": "c1", "decision_reason": "Сильный outcome fit", "next_test": "Макет 1:1"},
            {"id": "c2", "decision_reason": "Простое производство", "next_test": "Пробная сборка"},
        ],
        "semantic_review": {
            "status": "pass",
            "performed_by": "assistant",
            "reviewed_axes": [
                "material_family",
                "fabrication_process",
                "physical_behavior",
                "interaction_mode",
                "mechanism",
                "constraints",
                "shortlist",
            ],
            "notes": "Синонимы и косметические дубли удалены",
        },
    }


def test_validator_accepts_feasible_covered_fan() -> None:
    module = load_validator()
    assert module.validate_document(valid_document()) == []


def test_validator_allows_explained_axis_repeats_when_coverage_holds() -> None:
    module = load_validator()
    document = valid_document(6)
    document["concepts"][5]["primary_material_family"] = "cellulose"
    document["concepts"][5]["primary_fabrication_process"] = "fold_score"

    assert module.validate_document(document) == []


@pytest.mark.parametrize("concept_count", [4, 8])
def test_validator_enforces_five_to_seven_concepts(concept_count: int) -> None:
    module = load_validator()
    document = valid_document(concept_count)

    errors = module.validate_document(document)

    assert any("Нужно 5–7 концепций" in error for error in errors)


def test_validator_rejects_declared_field_type_violations() -> None:
    module = load_validator()
    document = valid_document()
    document["concepts"][0]["target_action"] = 42
    document["concepts"][1]["relative_cost"] = True
    document["concepts"][2]["risks"] = {"not": "a list"}

    errors = module.validate_document(document)

    assert any("target_action должен быть непустой строкой" in error for error in errors)
    assert any("relative_cost должен быть" in error for error in errors)
    assert any("risks должен быть непустым списком строк" in error for error in errors)


def test_validator_rejects_unknown_category_and_insufficient_interaction_coverage() -> None:
    module = load_validator()
    document = valid_document()
    document["concepts"][0]["primary_material_family"] = "kraft_paper"
    for concept in document["concepts"]:
        concept["interaction_mode"] = "observe"

    errors = module.validate_document(document)

    assert any("primary_material_family должен быть" in error for error in errors)
    assert any("Coverage interaction_mode" in error for error in errors)


def test_validator_rejects_failed_constraint_in_concept() -> None:
    module = load_validator()
    document = valid_document()
    document["concepts"][4]["constraint_results"][0]["status"] = "fail"

    errors = module.validate_document(document)

    assert any("должен быть удалён" in error for error in errors)


def test_validator_rejects_unknown_hard_constraint_in_shortlist() -> None:
    module = load_validator()
    document = valid_document()
    document["concepts"][1]["constraint_results"][0]["status"] = "unknown"

    errors = module.validate_document(document)

    assert any("без pass по всем hard constraints" in error for error in errors)


def test_validator_rejects_dominated_shortlist_concept() -> None:
    module = load_validator()
    document = valid_document()
    for score in document["concepts"][1]["criterion_scores"]:
        score["score"] = 1

    errors = module.validate_document(document)

    assert any("Shortlist concept c2 доминируется" in error for error in errors)


def test_validator_requires_best_weighted_concept_in_shortlist() -> None:
    module = load_validator()
    document = valid_document()
    document["shortlist"] = [
        {"id": "c2", "decision_reason": "Простое производство", "next_test": "Пробная сборка"},
        {"id": "c3", "decision_reason": "Высокая обновляемость", "next_test": "Тест замены"},
    ]

    errors = module.validate_document(document)

    assert any("максимальным weighted score: c1" in error for error in errors)


def test_validator_requires_complete_semantic_review() -> None:
    module = load_validator()
    document = valid_document()
    document["semantic_review"]["status"] = "pending"
    document["semantic_review"]["reviewed_axes"] = ["material_family"]

    errors = module.validate_document(document)

    assert any("semantic_review.status должен быть pass" in error for error in errors)
    assert any("semantic_review не покрыл оси" in error for error in errors)


def test_cli_returns_nonzero_for_oversized_fan(tmp_path: Path) -> None:
    input_path = tmp_path / "fan.json"
    input_path.write_text(json.dumps(valid_document(8), ensure_ascii=False), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(input_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Нужно 5–7 концепций" in result.stdout


def test_eval_gate_declares_ten_cases_and_not_run_status() -> None:
    rubric = (SKILL_DIR / "references" / "eval-rubric.md").read_text(encoding="utf-8")
    registry = yaml.safe_load((SKILL_DIR / "skill.yaml").read_text(encoding="utf-8"))

    assert rubric.count("### Case ") == 10
    assert registry["evaluation"] == {
        "status": "not-run",
        "required_before_team_ready": True,
        "rubric": "references/eval-rubric.md",
        "minimum_cases": 10,
    }
