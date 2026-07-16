from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "plugins" / "team-skills" / "skills" / "physical-solution-diversifier"
SCRIPT = SKILL_DIR / "scripts" / "validate_concept_fan.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_concept_fan", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_concept(index: int) -> dict:
    return {
        "id": f"c{index}",
        "name": f"Концепция {index}",
        "target_action": f"Действие {index}",
        "mechanism": f"Механизм {index}",
        "primary_material_class": f"Материал {index}",
        "primary_technology": f"Технология {index}",
        "primary_physical_behavior": f"Поведение {index}",
        "interaction": f"Взаимодействие {index}",
        "use_conditions": "Помещение",
        "production_complexity": "средняя",
        "cost_class": "средний; предположение",
        "risks": ["Риск прототипа"],
        "prototype_check": "Проверить механизм",
    }


def valid_document() -> dict:
    return {
        "concepts": [make_concept(index) for index in range(1, 6)],
        "shortlist": ["c1", "c3"],
    }


def test_validator_accepts_five_distinct_concepts() -> None:
    module = load_validator()
    assert module.validate_document(valid_document()) == []


def test_validator_rejects_cosmetic_duplicate_and_bad_shortlist() -> None:
    module = load_validator()
    document = valid_document()
    document["concepts"][4]["primary_technology"] = document["concepts"][0]["primary_technology"]
    document["shortlist"] = ["c1", "missing"]

    errors = module.validate_document(document)

    assert any("primary_technology" in error for error in errors)
    assert any("неизвестные id" in error for error in errors)


def test_cli_returns_nonzero_for_too_small_fan(tmp_path: Path) -> None:
    document = valid_document()
    document["concepts"] = document["concepts"][:4]
    input_path = tmp_path / "fan.json"
    input_path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(input_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Нужно минимум 5 концепций" in result.stdout
