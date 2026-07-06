from __future__ import annotations

import re
from pathlib import Path

from conftest import ROOT, skill_dirs


SURVEY_HEADING = "## Опрос После Использования"
LOGGING_HEADING = "## Логирование Сбоев"
TEMPLATE_SCRIPT = ROOT / "scripts" / "templates" / "log_usage_feedback.py"


def survey_section(skill_dir: Path) -> str:
    content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert SURVEY_HEADING in content, f"{skill_dir.name} должен содержать секцию «{SURVEY_HEADING}»"
    section = content.split(SURVEY_HEADING, 1)[1]
    return section.split("\n## ", 1)[0]


def test_all_skills_have_usage_feedback_survey() -> None:
    for skill_dir in skill_dirs():
        section = survey_section(skill_dir)
        name = skill_dir.name
        required = [
            f"1. Что в этом использовании {name} было полезно?",
            "2. Что стоит доработать в skill или его формате?",
            '"пропустить"',
            f"~/.codex/skill-runs/{name}/usage-feedback.jsonl",
            "scripts/log_usage_feedback.py",
            "не делайте вид, что лог сохранён",
            "не коммитить",
        ]
        for phrase in required:
            assert phrase in section, f"{name}: в секции опроса нет обязательной строки {phrase!r}"


def heading_position(content: str, heading: str, context: str) -> int:
    match = re.search(rf"(?m)^{re.escape(heading)}$", content)
    assert match, f"{context}: нет секции «{heading}»"
    return match.start()


def test_survey_comes_before_failure_logging() -> None:
    for skill_dir in skill_dirs():
        content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        survey_at = heading_position(content, SURVEY_HEADING, skill_dir.name)
        logging_at = heading_position(content, LOGGING_HEADING, skill_dir.name)
        assert survey_at < logging_at, (
            f"{skill_dir.name}: «{SURVEY_HEADING}» должен идти перед «{LOGGING_HEADING}»"
        )


def test_template_script_derives_skill_name_from_folder() -> None:
    content = TEMPLATE_SCRIPT.read_text(encoding="utf-8")
    assert "parents[1].name" in content, "шаблон скрипта должен выводить имя skill из имени папки, не хардкодить"
    assert "usage-feedback.jsonl" in content


def test_every_skill_ships_canonical_feedback_script() -> None:
    template = TEMPLATE_SCRIPT.read_text(encoding="utf-8")
    for skill_dir in skill_dirs():
        script = skill_dir / "scripts" / "log_usage_feedback.py"
        assert script.exists(), f"{skill_dir.name} должен иметь scripts/log_usage_feedback.py"
        assert script.read_text(encoding="utf-8") == template, (
            f"{skill_dir.name}: scripts/log_usage_feedback.py разошёлся с scripts/templates/log_usage_feedback.py; "
            "правьте шаблон и копируйте его во все skills"
        )


def test_new_skill_generator_creates_usage_feedback_contract() -> None:
    content = (ROOT / "scripts" / "new_skill.py").read_text(encoding="utf-8")
    assert SURVEY_HEADING in content
    assert "usage-feedback.jsonl" in content
    assert "log_usage_feedback.py" in content
    assert 'написать "пропустить"' in content
