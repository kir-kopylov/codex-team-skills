from __future__ import annotations

from conftest import load_frontmatter, skill_dirs


# Claude Code отдаёт модели список навыков как строки «имя: описание» и режет его
# по общему бюджету знаков: когда бюджет исчерпан, у оставшихся навыков описание
# до модели не доходит — остаётся голое имя, и обычная фраза пользователя в такой
# навык уже не попадает. Наблюдаемый бюджет — примерно 16 500 знаков на группу
# навыков, поэтому здесь стоит порог с запасом.
DESCRIPTION_BUDGET = 14_000


def skill_entries() -> list[tuple[str, str]]:
    entries = []
    for skill_dir in skill_dirs():
        frontmatter, _ = load_frontmatter(skill_dir / "SKILL.md")
        entries.append((frontmatter["name"], frontmatter["description"]))
    return entries


def test_sum_of_name_and_description_fits_budget() -> None:
    entries = skill_entries()
    assert entries, "Нужен хотя бы один skill"

    total = sum(len(name) + len(description) for name, description in entries)
    assert total <= DESCRIPTION_BUDGET, (
        f"Сумма «имя + description» по всем skills — {total} знаков при лимите {DESCRIPTION_BUDGET}. "
        "Список навыков обрежется, и часть навыков дойдёт до модели без описания. "
        "Сократите описания: триггерные фразы идут первыми, границы остаются в skill.yaml."
    )
