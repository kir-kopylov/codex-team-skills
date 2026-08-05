from __future__ import annotations

import re

from conftest import load_frontmatter, load_registry, skill_dirs


GATE_HEADING = "## Согласие На Запуск"

# Общие инварианты всех форматов; полный шаблон — в CONTRIBUTING.md.
GATE_REQUIRED_PHRASES = [
    "без вопроса",
    "выйдите из skill молча",
]

LEGACY_REQUIRED_PHRASES = ["Применить или решить без него?"]

COMPACT_USER_CONTRACT_MARKER = "Применить **«"
VERBOSE_USER_CONTRACT_MARKER = "Для вашей задачи —"

VERBOSE_USER_CONTRACT_REQUIRED_PHRASES = [
    VERBOSE_USER_CONTRACT_MARKER,
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

AUTHOR_RE = re.compile(r"@[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")


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


def gate_format(gate: str) -> str:
    if COMPACT_USER_CONTRACT_MARKER in gate:
        return "compact"
    if VERBOSE_USER_CONTRACT_MARKER in gate:
        return "verbose"
    return "legacy"


def valid_author(skill_dir) -> tuple[dict, str]:
    registry = load_registry(skill_dir)
    author_github = registry.get("author_github")
    assert isinstance(author_github, str) and AUTHOR_RE.fullmatch(author_github), (
        f"{skill_dir.name}: пользовательская карточка требует подтверждённый "
        "GitHub-аккаунт автора в author_github"
    )
    return registry, author_github


def test_consent_gate_is_first_section() -> None:
    # Гейт читается раньше любой инструкции skill: первый H2 в body — это гейт.
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

        format_name = gate_format(gate)
        if format_name == "compact":
            _assert_compact_contract(skill_dir, gate)
        elif format_name == "verbose":
            _assert_verbose_contract(skill_dir, gate)
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


def _assert_compact_contract(skill_dir, gate: str) -> None:
    registry, author_github = valid_author(skill_dir)

    for phrase in (
        "ровно три содержательные строки",
        "не более 45 слов",
        "по одной строке и одному предложению",
        "не повторяют запрос",
        "неизвестное не придумывайте",
        "`Annotation N`",
    ):
        assert phrase in gate, (
            f"{skill_dir.name}: компактный гейт не закрепляет правило {phrase!r}"
        )

    question_matches = list(
        re.finditer(
            rf"(?m)^Применить \*\*«(?P<title>[^»\n]+)»\*\* "
            rf"\((?P<meta>{re.escape(author_github)}(?:; [^)\n]+)?)\) "
            r"для (?P<task>[^\n]+)\?$",
            gate,
        )
    )
    with_matches = list(
        re.finditer(r"(?m)^\*\*С навыком:\*\* (?P<text>[^\n]+)$", gate)
    )
    without_matches = list(
        re.finditer(r"(?m)^\*\*Без навыка:\*\* (?P<text>[^\n]+)$", gate)
    )
    assert len(question_matches) == len(with_matches) == len(without_matches) == 1, (
        f"{skill_dir.name}: компактная карточка должна содержать по одной "
        "строке вопроса, «С навыком» и «Без навыка»"
    )

    question = question_matches[0].group(0)
    with_line = with_matches[0].group(0)
    without_line = without_matches[0].group(0)
    card = f"{question}\n\n{with_line}\n\n{without_line}"
    assert card in gate, (
        f"{skill_dir.name}: три строки карточки должны идти подряд "
        "без дополнительного абзаца"
    )
    assert len([line for line in card.splitlines() if line]) == 3

    words = re.findall(r"(?u)\b[\w@][\w@-]*\b", card)
    assert len(words) <= 45, (
        f"{skill_dir.name}: шаблон компактной карточки содержит {len(words)} слов"
    )

    for label, match in (
        ("С навыком", with_matches[0]),
        ("Без навыка", without_matches[0]),
    ):
        comparison = match.group("text")
        assert comparison.endswith("."), (
            f"{skill_dir.name}: строка «{label}» должна быть одним предложением"
        )
        assert not re.search(r"[.!?]", comparison[:-1]), (
            f"{skill_dir.name}: строка «{label}» содержит больше одного предложения"
        )

    comparison_text = f"{with_line}\n{without_line}".lower()
    for repeated_detail in ("действие", "объект"):
        assert repeated_detail not in comparison_text, (
            f"{skill_dir.name}: сравнительные строки повторяют {repeated_detail!r} "
            "вместо показа только различия"
        )

    assert "Автор навыка" not in card
    assert not re.search(r"(?m)^\s*\|.*\|\s*$", card)
    assert not re.search(r"(?m)^Annotation \d+", card)
    assert skill_dir.name not in card, (
        f"{skill_dir.name}: карточка не должна показывать внутреннее имя"
    )
    if registry.get("status") != "experimental" and registry["owner"] != author_github:
        assert registry["owner"] not in card, (
            f"{skill_dir.name}: owner нельзя выдавать за автора"
        )
    for jargon in ("team skill", "live-state", "Пользовательский контракт"):
        assert jargon not in card, (
            f"{skill_dir.name}: карточка содержит служебное выражение {jargon!r}"
        )


def _assert_verbose_contract(skill_dir, gate: str) -> None:
    for phrase in VERBOSE_USER_CONTRACT_REQUIRED_PHRASES:
        assert phrase in gate, (
            f"{skill_dir.name}: в подробной карточке нет обязательной "
            f"фразы «{phrase}»"
        )

    registry, author_github = valid_author(skill_dir)
    assert f"Автор навыка — **{author_github}**." in gate, (
        f"{skill_dir.name}: карточка должна показывать GitHub-аккаунт "
        "автора, а не имя, фамилию или owner"
    )

    for phrase in REQUEST_DETAIL_PHRASES:
        assert phrase in gate, (
            f"{skill_dir.name}: гейт не требует перенести из запроса {phrase!r}"
        )

    match = re.search(
        rf"({re.escape(VERBOSE_USER_CONTRACT_MARKER)}.*?"
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
    with_skill = re.search(
        r"> \*\*С навыком\*\*\n>\n(?P<text>.*?)(?=\n\n> \*\*Без навыка\*\*)",
        user_block,
        re.DOTALL,
    )
    without_skill = re.search(
        r"> \*\*Без навыка\*\*\n>\n(?P<text>.*?)(?=\n\n\*\*)",
        user_block,
        re.DOTALL,
    )
    assert with_skill and without_skill, (
        f"{skill_dir.name}: оба блока сравнения должны содержать "
        "отдельный полный текст"
    )
    for label, comparison in (
        ("С навыком", with_skill.group("text")),
        ("Без навыка", without_skill.group("text")),
    ):
        for detail in ("действие пользователя", "количеств", "проверяем"):
            assert detail in comparison, (
                f"{skill_dir.name}: блок «{label}» должен явно повторять "
                f"{detail!r} из запроса"
            )
    assert not re.search(r"(?m)^\s*\|.*\|\s*$", user_block), (
        f"{skill_dir.name}: карточка не должна использовать таблицу"
    )

    assert skill_dir.name not in user_block, (
        f"{skill_dir.name}: пользовательский блок не должен "
        "показывать внутреннее имя"
    )
    if registry.get("status") != "experimental" and registry["owner"] != author_github:
        assert registry["owner"] not in user_block, (
            f"{skill_dir.name}: owner нельзя выдавать за автора"
        )
    for jargon in ("team skill", "live-state", "Пользовательский контракт"):
        assert jargon not in user_block, (
            f"{skill_dir.name}: пользовательский блок содержит "
            f"служебное выражение {jargon!r}"
        )
    assert "полных предложен" in gate, (
        f"{skill_dir.name}: сравнение должно состоять из полных предложений"
    )
    assert "в обоих блоках повторены объект, количество" in gate, (
        f"{skill_dir.name}: подробный гейт должен требовать повторить детали"
    )
    assert "неизвестное не придумывайте" in gate, (
        f"{skill_dir.name}: неизвестные детали запроса нельзя достраивать"
    )


def test_experimental_gate_carries_label_and_owner() -> None:
    # Экспериментальный skill обязан представляться пометкой и owner-ом.
    for skill_dir in skill_dirs():
        registry = load_registry(skill_dir)
        gate = gate_section(skill_dir)
        format_name = gate_format(gate)
        if registry.get("status") == "experimental":
            if format_name in {"compact", "verbose"}:
                assert "экспериментальн" in gate.lower(), (
                    f"{skill_dir.name}: пользовательская карточка experimental "
                    "skill должна показывать экспериментальный статус"
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
                f"{skill_dir.name}: пометка «экспериментальный» допустима "
                "только при status: experimental"
            )
