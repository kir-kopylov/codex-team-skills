from __future__ import annotations

import re

from conftest import load_frontmatter, load_registry, skill_dirs


GATE_HEADING = "## Согласие На Запуск"

# Общие инварианты старого и нового форматов; полный шаблон — в CONTRIBUTING.md
GATE_REQUIRED_PHRASES = [
    "без вопроса",
    "выйдите из skill молча",
]

LEGACY_REQUIRED_PHRASES = ["Применить или решить без него?"]

USER_CONTRACT_MARKER = "Для вашей задачи —"

USER_CONTRACT_REQUIRED_PHRASES = [
    USER_CONTRACT_MARKER,
    "может пригодиться командный навык",
    "Автор навыка — **",
    "> **С навыком**",
    "> **Без навыка**",
    "**Применить навык?**",
]

REQUEST_DETAIL_PHRASES = [
    "действие пользователя",
    "конкретный объект",
    "запрошенное количество",
    "проверяемые сведения",
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
        for phrase in GATE_REQUIRED_PHRASES:
            assert phrase in gate, (
                f"{skill_dir.name}: в гейте нет обязательной фразы «{phrase}»"
            )
        assert re.search(r"ждите ответ(?:а)?", gate), (
            f"{skill_dir.name}: гейт не требует дождаться ответа пользователя"
        )

        if USER_CONTRACT_MARKER in gate:
            for phrase in USER_CONTRACT_REQUIRED_PHRASES:
                assert phrase in gate, (
                    f"{skill_dir.name}: в карточке пользовательского контракта "
                    f"нет обязательной фразы «{phrase}»"
                )

            registry = load_registry(skill_dir)
            author_github = registry.get("author_github")
            assert isinstance(author_github, str) and re.fullmatch(
                r"@[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?",
                author_github,
            ), (
                f"{skill_dir.name}: новая карточка требует подтверждённый "
                "GitHub-аккаунт автора в author_github"
            )
            assert f"Автор навыка — **{author_github}**." in gate, (
                f"{skill_dir.name}: карточка должна показывать GitHub-аккаунт "
                "автора, а не имя, фамилию или owner"
            )

            for phrase in REQUEST_DETAIL_PHRASES:
                assert phrase in gate, (
                    f"{skill_dir.name}: гейт не требует перенести из запроса "
                    f"{phrase!r}"
                )

            match = re.search(
                rf"({re.escape(USER_CONTRACT_MARKER)}.*?"
                r"\*\*Применить навык\?\*\*)",
                gate,
                re.DOTALL,
            )
            assert match, (
                f"{skill_dir.name}: не найдена цельная Markdown-карточка "
                "от подводки к задаче до вопроса"
            )
            user_block = match.group(1)

            assert user_block.index("> **С навыком**") < user_block.index(
                "> **Без навыка**"
            ), (
                f"{skill_dir.name}: сначала покажите результат с навыком, "
                "затем ограничение без навыка"
            )
            assert not re.search(r"(?m)^\s*\|.*\|\s*$", user_block), (
                f"{skill_dir.name}: карточка не должна использовать таблицу: "
                "в интерфейсе колонки слипаются"
            )

            assert skill_dir.name not in user_block, (
                f"{skill_dir.name}: пользовательский блок не должен "
                "показывать внутреннее имя"
            )
            if (
                registry.get("status") != "experimental"
                and registry["owner"] != author_github
            ):
                assert registry["owner"] not in user_block, (
                    f"{skill_dir.name}: owner нельзя выдавать за автора, "
                    "когда навык не экспериментальный"
                )
            for jargon in ("team skill", "live-state", "Пользовательский контракт"):
                assert jargon not in user_block, (
                    f"{skill_dir.name}: пользовательский блок содержит "
                    f"служебное выражение {jargon!r}"
                )
            assert "полных предложен" in gate, (
                f"{skill_dir.name}: сравнение должно состоять из полных "
                "предложений, а не обрезанных подписей"
            )
            assert "в обоих блоках повторены объект, количество" in gate, (
                f"{skill_dir.name}: гейт должен требовать явно повторить "
                "объект, количество и сведения в обоих блоках"
            )
            assert "неизвестное не придумывайте" in gate, (
                f"{skill_dir.name}: неизвестные детали запроса нельзя "
                "достраивать ради заполнения карточки"
            )
        else:
            assert f"team skill `{skill_dir.name}`" in gate, (
                f"{skill_dir.name}: старый гейт должен называть skill "
                "по имени в backticks"
            )
            for phrase in LEGACY_REQUIRED_PHRASES:
                assert phrase in gate, (
                    f"{skill_dir.name}: в старом гейте нет обязательной "
                    f"фразы «{phrase}»"
                )


def test_experimental_gate_carries_label_and_owner() -> None:
    # Экспериментальный skill обязан представляться пометкой и owner-ом,
    # а у остальных статусов пометка не должна оставаться после повышения
    for skill_dir in skill_dirs():
        registry = load_registry(skill_dir)
        gate = gate_section(skill_dir)
        if registry.get("status") == "experimental":
            if USER_CONTRACT_MARKER in gate:
                assert "экспериментальн" in gate.lower(), (
                    f"{skill_dir.name}: новая карточка experimental skill "
                    "должна показывать экспериментальный статус"
                )
            else:
                assert f"экспериментальный team skill `{skill_dir.name}`" in gate, (
                    f"{skill_dir.name}: старый гейт experimental skill должен "
                    "представляться как «экспериментальный team skill»"
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
