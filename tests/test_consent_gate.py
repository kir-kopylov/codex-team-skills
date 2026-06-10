from __future__ import annotations

import re

from conftest import load_frontmatter, load_registry, skill_dirs


GATE_HEADING = "## Согласие На Запуск"

# Инварианты канонического текста гейта; полный шаблон — в CONTRIBUTING.md
GATE_REQUIRED_PHRASES = [
    "без вопроса",
    "Применить или решить без него?",
    "выйдите из skill молча",
]


def gate_section(skill_dir) -> str:
    """Вернуть текст секции гейта (от заголовка до следующего H2)."""
    _, body = load_frontmatter(skill_dir / "SKILL.md")
    match = re.search(
        rf"^{re.escape(GATE_HEADING)}\n(.*?)(?=^## |\Z)",
        body,
        re.MULTILINE | re.DOTALL,
    )
    assert match, f"{skill_dir.name}: SKILL.md не содержит секцию «{GATE_HEADING}»"
    return match.group(1)


def test_consent_gate_is_first_section() -> None:
    # Гейт читается раньше любой инструкции skill: первый H2 в body — это гейт
    for skill_dir in skill_dirs():
        _, body = load_frontmatter(skill_dir / "SKILL.md")
        headings = [line for line in body.splitlines() if line.startswith("## ")]
        assert headings, f"{skill_dir.name}: SKILL.md без секций"
        assert headings[0] == GATE_HEADING, (
            f"{skill_dir.name}: первой секцией SKILL.md должен быть «{GATE_HEADING}», "
            f"а не «{headings[0]}»"
        )


def test_consent_gate_has_canonical_contract() -> None:
    for skill_dir in skill_dirs():
        gate = gate_section(skill_dir)
        assert f"team skill `{skill_dir.name}`" in gate, (
            f"{skill_dir.name}: гейт должен называть skill по имени в backticks"
        )
        for phrase in GATE_REQUIRED_PHRASES:
            assert phrase in gate, (
                f"{skill_dir.name}: в гейте нет обязательной фразы «{phrase}»"
            )


def test_experimental_gate_carries_label_and_owner() -> None:
    # Экспериментальный skill обязан представляться пометкой и owner-ом,
    # а у остальных статусов пометка не должна оставаться после повышения
    for skill_dir in skill_dirs():
        registry = load_registry(skill_dir)
        gate = gate_section(skill_dir)
        if registry.get("status") == "experimental":
            assert f"экспериментальный team skill `{skill_dir.name}`" in gate, (
                f"{skill_dir.name}: experimental skill должен представляться "
                "как «экспериментальный team skill»"
            )
            assert registry["owner"] in gate, (
                f"{skill_dir.name}: гейт experimental skill должен называть owner "
                "для обратной связи"
            )
        else:
            assert "экспериментальн" not in gate.lower(), (
                f"{skill_dir.name}: пометка «экспериментальный» в гейте допустима "
                "только при status: experimental — уберите её при смене статуса"
            )
