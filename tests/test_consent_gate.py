from __future__ import annotations

import re

from conftest import load_frontmatter, load_registry, skill_dirs


GATE_HEADING = "## Согласие На Запуск"

# Общие инварианты гейта; полный шаблон — в CONTRIBUTING.md.
GATE_REQUIRED_PHRASES = [
    "без вопроса",
    "выйдите из skill молча",
]

COMPACT_USER_CONTRACT_MARKER = "Применить **«"
FORBIDDEN_USER_CONTRACT_MARKERS = [
    "Для вашей задачи —",
    "Применить или решить без него?",
]

AUTHOR_RE = re.compile(r"@[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
SELF_CHECK_RE = re.compile(r"(?m)^Перед отправкой\b")


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
        for marker in FORBIDDEN_USER_CONTRACT_MARKERS:
            assert marker not in gate, (
                f"{skill_dir.name}: старый маркер {marker!r} больше не допустим"
            )
        assert COMPACT_USER_CONTRACT_MARKER in gate, (
            f"{skill_dir.name}: допустима только короткая карточка"
        )
        _assert_compact_contract(skill_dir, gate)


def _assert_compact_contract(skill_dir, gate: str) -> None:
    registry, author_github = valid_author(skill_dir)
    if registry.get("status") == "experimental":
        question_meta = (
            f"{author_github}; экспериментальный; "
            f"обратная связь {registry['owner']}"
        )
    else:
        question_meta = author_github

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
            rf"\((?P<meta>{re.escape(question_meta)})\) "
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
    if registry.get("status") == "experimental":
        card_preamble = gate[: question_matches[0].start()]
        assert "экспериментальн" not in card_preamble.lower(), (
            f"{skill_dir.name}: экспериментальный статус нельзя дублировать "
            "отдельным абзацем перед первой строкой карточки"
        )
        assert registry["owner"] not in card_preamble, (
            f"{skill_dir.name}: контакт owner нельзя выносить в отдельный "
            "абзац перед первой строкой карточки"
        )
    self_check = SELF_CHECK_RE.search(gate, question_matches[0].end())
    assert self_check, (
        f"{skill_dir.name}: после карточки нет инструкции самопроверки"
    )
    visible_lines = [
        line.strip()
        for line in gate[question_matches[0].start() : self_check.start()].splitlines()
        if line.strip()
    ]
    assert visible_lines == [question, with_line, without_line], (
        f"{skill_dir.name}: между вопросом и инструкцией самопроверки должны быть "
        "ровно три непустые видимые строки: вопрос, «С навыком» и «Без навыка»"
    )
    card = "\n".join(visible_lines)

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


def test_experimental_gate_carries_label_and_owner() -> None:
    # Статус experimental и контакт owner показываются внутри строки вопроса.
    for skill_dir in skill_dirs():
        registry = load_registry(skill_dir)
        gate = gate_section(skill_dir)
        if registry.get("status") == "experimental":
            _, author_github = valid_author(skill_dir)
            expected_meta = (
                f"({author_github}; экспериментальный; "
                f"обратная связь {registry['owner']})"
            )
            question_line = next(
                (
                    line
                    for line in gate.splitlines()
                    if line.startswith(COMPACT_USER_CONTRACT_MARKER)
                ),
                "",
            )
            assert expected_meta in question_line, (
                f"{skill_dir.name}: статус experimental и контакт owner должны "
                "находиться внутри первой строки карточки"
            )
        else:
            assert "экспериментальн" not in gate.lower(), (
                f"{skill_dir.name}: пометка «экспериментальный» допустима "
                "только при status: experimental"
            )
