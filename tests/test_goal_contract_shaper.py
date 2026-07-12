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


def test_goal_contract_shaper_has_optional_runtime_handoff() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    reference = (SKILL_DIR / "references" / "runtime-handoff.md").read_text(
        encoding="utf-8"
    )

    for fragment in (
        "goalrt contract compile",
        "goalrt contract validate",
        "goalrt contract render-goal",
        "Не запускайте `goalrt run start`",
        "PARTIAL_ENFORCEMENT",
    ):
        assert fragment in content

    assert "Shaper не копирует schema" in reference
    assert "supervised" in reference


def test_goal_contract_shaper_registers_runtime_boundary_examples() -> None:
    registry = load_registry(SKILL_DIR)
    expected = {
        "examples/good-07-runtime-contract.md",
        "examples/good-08-runtime-missing-fallback.md",
        "examples/anti-07-unsupported-tools-enforced.md",
        "examples/anti-08-hard-token-budget.md",
    }

    assert expected <= set(registry["example_files"])
