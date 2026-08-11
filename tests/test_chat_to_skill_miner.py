from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "plugins" / "team-skills" / "skills" / "chat-to-skill-miner"


def test_chat_to_skill_miner_has_a_narrow_pipeline_boundary() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    assert "ранжированный список" in text
    assert "skill-methodologist" in text
    assert "razbor-chata-na-artefakty" in text
    assert "Не запускайте его по умолчанию" in text
    assert "не проектируйте полный workflow" in text
    assert "MacBook" not in text


def test_chat_to_skill_miner_template_stops_before_contract_design() -> None:
    template = (SKILL_DIR / "references" / "output-template.md").read_text(
        encoding="utf-8"
    )

    assert "## Передача После Выбора" in template
    assert "skill-methodologist" in template
    assert "Полный контракт" in template
    assert "признаки проверяемости" in template
    assert "Implementation-Ready" not in template


def test_chat_to_skill_miner_is_team_ready_and_has_five_examples() -> None:
    registry = yaml.safe_load((SKILL_DIR / "skill.yaml").read_text(encoding="utf-8"))

    assert registry["status"] == "team-ready"
    assert len(registry["example_files"]) == 5
    for relative_path in registry["example_files"]:
        assert (SKILL_DIR / relative_path).is_file()
