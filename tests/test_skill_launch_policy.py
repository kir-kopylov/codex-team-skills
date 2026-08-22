from __future__ import annotations

import re

from conftest import ROOT, load_frontmatter, load_registry, skill_dirs


LAUNCH_HEADING = "## Запуск Навыка"
V3_EXPLICIT_ONLY = "goal-contract-shaper-v3"
SCREENCAST_SPEEDUP = (
    ROOT / "plugins" / "team-skills" / "skills" / "screencast-speedup"
)
WORD_RE = re.compile(r"(?u)\b[\w@][\w@-]*\b")

OLD_LAUNCH_MARKERS = (
    "## Согласие На Запуск",
    "Применить **«",
    "Применить навык?",
    "Применить или",
    "С навыком",
    "Без навыка",
    "ждите ответа",
    "ждите ответ",
    "дождитесь ответа",
    "при отказе",
    "молча",
    "выйдите из skill молча",
    "решите задачу с нуля",
)

COMMON_POLICY_MARKERS = (
    "ровно одну короткую контекстную строку (не более 30 слов)",
    "продолжайте работу в том же ответе, не ожидая реакции",
    "пересказ всего запроса",
    "совместимые навыки",
    "минимальный набор",
    "одну общую строку",
    "несовместимым результатам",
    "и запрос не позволяет выбрать",
    "желаемом результате",
    "не о разрешении применить навык",
    "Запуск навыка не расширяет полномочия",
    "Выполните всю безопасную и уже разрешённую часть",
    "только непосредственно перед ещё не разрешённым внешним или изменяющим действием",
    "Не запрашивайте повторно уже данное разрешение",
    "не дублируйте системное окно подтверждения",
)


def launch_section(skill_dir) -> str:
    """Вернуть секцию запуска от первого H2 до следующего H2."""
    _, body = load_frontmatter(skill_dir / "SKILL.md")
    match = re.search(
        rf"^{re.escape(LAUNCH_HEADING)}\n(.*?)(?=^## |\Z)",
        body,
        re.MULTILINE | re.DOTALL,
    )
    assert match, f"{skill_dir.name}: нет секции «{LAUNCH_HEADING}»"
    return match.group(1)


def notice_line(skill_dir, section: str) -> str:
    lines = [line.strip() for line in section.splitlines() if line.startswith("Применяю ")]
    assert len(lines) == 1, (
        f"{skill_dir.name}: в секции запуска должна быть ровно одна строка "
        "шаблона уведомления"
    )
    return lines[0]


def test_skill_launch_is_first_section() -> None:
    for skill_dir in skill_dirs():
        _, body = load_frontmatter(skill_dir / "SKILL.md")
        headings = [line for line in body.splitlines() if line.startswith("## ")]
        assert headings, f"{skill_dir.name}: SKILL.md без секций"
        assert headings[0] == LAUNCH_HEADING, (
            f"{skill_dir.name}: первой секцией должна быть «{LAUNCH_HEADING}», "
            f"а не «{headings[0]}»"
        )
        assert not re.search(r"(?m)^## Согласие На Запуск$", body), (
            f"{skill_dir.name}: старый заголовок запуска больше не допустим"
        )


def test_notice_template_matches_status_and_current_request() -> None:
    for skill_dir in skill_dirs():
        registry = load_registry(skill_dir)
        status = registry["status"]
        owner = re.escape(registry["owner"])
        line = notice_line(skill_dir, launch_section(skill_dir))

        if status == "team-ready":
            pattern = (
                r"^Применяю \*\*«(?P<title>[^»\n]+)»\*\*: "
                r"(?P<context><[^>\n]+>); продолжаю без ожидания\.$"
            )
            assert "@" not in line, (
                f"{skill_dir.name}: готовый навык не показывает автора или owner"
            )
            author_github = registry.get("author_github")
            if isinstance(author_github, str):
                assert author_github not in line
            for author in registry.get("authors", []):
                assert author not in line
        elif status == "experimental":
            pattern = (
                r"^Применяю экспериментальный навык "
                r"\*\*«(?P<title>[^»\n]+)»\*\* "
                rf"\(обратная связь — {owner}\): "
                r"(?P<context><[^>\n]+>); продолжаю без ожидания\.$"
            )
        elif status == "draft":
            pattern = (
                r"^Применяю черновой навык "
                r"\*\*«(?P<title>[^»\n]+)»\*\* "
                rf"\(обратная связь — {owner}\): "
                r"(?P<context><[^>\n]+>); продолжаю без ожидания\.$"
            )
        else:
            raise AssertionError(f"{skill_dir.name}: неизвестный режим запуска {status!r}")

        match = re.fullmatch(pattern, line)
        assert match, (
            f"{skill_dir.name}: шаблон уведомления не соответствует status: {status}"
        )
        assert "текущего запроса" in match.group("context"), (
            f"{skill_dir.name}: уведомление не требует привязки к текущему запросу"
        )
        assert skill_dir.name not in line, (
            f"{skill_dir.name}: уведомление показывает внутреннее имя папки"
        )
        assert "?" not in line, (
            f"{skill_dir.name}: уведомление не должно быть вопросом"
        )
        assert len(WORD_RE.findall(line)) <= 30, (
            f"{skill_dir.name}: шаблон уведомления длиннее 30 слов"
        )


def test_ready_and_experimental_are_immediate_but_drafts_are_explicit_only() -> None:
    for skill_dir in skill_dirs():
        registry = load_registry(skill_dir)
        section = launch_section(skill_dir)

        if skill_dir.name == V3_EXPLICIT_ONLY:
            assert "только при явном вызове `goal-contract-shaper-v3`" in section
            assert (
                "Смысловой запрос без прямого вызова маршрутизируйте в базовый "
                "`goal-contract-shaper`"
            ) in section
            assert "не запускайте v3 и не спрашивайте о его применении" in section
        elif registry["status"] == "draft":
            assert "только при явном вызове по имени или прямой команде пользователя" in section
            assert "При одном смысловом совпадении не запускайте навык" in section
            assert "не спрашивайте о его применении" in section
        else:
            assert (
                "При явном вызове или однозначном смысловом совпадении "
                "применяйте навык сразу"
            ) in section


def test_launch_policy_keeps_choices_and_authority_separate() -> None:
    for skill_dir in skill_dirs():
        section = launch_section(skill_dir)
        for marker in COMMON_POLICY_MARKERS:
            assert marker in section, (
                f"{skill_dir.name}: секция запуска не закрепляет правило {marker!r}"
            )


def test_screencast_notice_cannot_replace_read_only_source_discovery() -> None:
    content = (SCREENCAST_SPEEDUP / "SKILL.md").read_text(encoding="utf-8")

    for fragment in (
        "Не завершайте первый ответ строкой уведомления или обещанием будущей разведки",
        "самостоятельно выполните доступный read-only поиск исходника",
        "read-only `stat` и `ffprobe`",
        "задайте один ближайший вопрос о выборе файла",
        "задайте один ближайший вопрос о лимите",
        "Не задавайте оба вопроса сразу",
        "не переспрашивай уже названное значение",
    ):
        assert fragment in content

    assert "дождись подтверждения" not in content
    assert "задавай его всегда" not in content


def test_old_consent_and_silent_refusal_markers_are_absent() -> None:
    for skill_dir in skill_dirs():
        section = launch_section(skill_dir)
        lowered = section.lower()
        assert "?" not in section, (
            f"{skill_dir.name}: секция запуска содержит блокирующий вопрос"
        )
        for marker in OLD_LAUNCH_MARKERS:
            assert marker.lower() not in lowered, (
                f"{skill_dir.name}: остался старый маркер запуска {marker!r}"
            )
