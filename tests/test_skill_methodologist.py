from __future__ import annotations

from conftest import ROOT, load_registry


SKILL_DIR = ROOT / "plugins" / "team-skills" / "skills" / "skill-methodologist"


def test_skill_methodologist_preserves_dmitry_gvozdetsky_authorship() -> None:
    registry = load_registry(SKILL_DIR)
    skill_body = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    reference_body = (SKILL_DIR / "references" / "skill-methodology.md").read_text(encoding="utf-8")

    assert registry["owner"] == "@kir-kopylov"
    assert "Дмитрий Гвоздецкий" in registry.get("authors", [])
    assert "Дмитрием Гвоздецким" in registry["source_asset"]
    assert "Дмитрием Гвоздецким" in skill_body
    assert "Дмитрием Гвоздецким" in reference_body


def test_skill_methodologist_respects_late_requirement_corrections() -> None:
    skill_body = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    reference_body = (
        SKILL_DIR / "references" / "skill-methodology.md"
    ).read_text(encoding="utf-8")
    example_body = (
        SKILL_DIR / "examples" / "good-01-chat-to-skill-contract.md"
    ).read_text(encoding="utf-8")

    statuses = (
        "`действует`",
        "`отменено позднейшим уточнением`",
        "`исследовательская идея`",
    )
    for status in statuses:
        assert status in skill_body
        assert status in reference_body
        assert status in example_body

    assert "Позднее прямое ограничение пользователя имеет приоритет" in skill_body
    assert "В итоговый контракт входят только действующие требования" in reference_body
    assert "возвращать публикацию как «необязательный режим»" in example_body
