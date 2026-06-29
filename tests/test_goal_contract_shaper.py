from __future__ import annotations

from conftest import ROOT, load_registry


SKILL_DIR = ROOT / "plugins" / "team-skills" / "skills" / "goal-contract-shaper"


def test_goal_contract_shaper_keeps_universal_value_grammar() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    required_fragments = [
        "Универсальная Грамматика Деятельности",
        "Объект и ценность",
        "Финал и управление",
        "Роли",
        "Единицы процесса",
        "Человек внутри цикла",
        "Ожидание и зависание",
        "Стоимость и риск",
        "Журнал круга",
        "автономный агент там, где нужен человек",
    ]

    for fragment in required_fragments:
        assert fragment in content


def test_goal_contract_shaper_links_value_creation_example() -> None:
    registry = load_registry(SKILL_DIR)
    assert "examples/good-04-value-creation-cycle.md" in registry["example_files"]

    example = (SKILL_DIR / "examples" / "good-04-value-creation-cycle.md").read_text(
        encoding="utf-8"
    )
    assert "процесс создания ценности" in example
    assert "единицу потери" in example
    assert "сопровождаемый человеческий цикл" in example
