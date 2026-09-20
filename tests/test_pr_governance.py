from __future__ import annotations

import importlib.util
from pathlib import Path

from conftest import ROOT


SCRIPT_PATH = ROOT / "scripts" / "check_pr_governance.py"
PR_TEMPLATE_PATH = ROOT / ".github" / "pull_request_template.md"
CONTRIBUTING_PATH = ROOT / "CONTRIBUTING.md"

PR_DESCRIPTION_LAYOUT = (
    ("## Проблема", ("- Какую боль решает:", "- Для кого:")),
    ("## Что изменилось", ("- Было:", "- Стало:")),
    ("## Границы", ("- Когда не использовать:", "- Что не меняется:")),
    (
        "## Доказательства",
        ("- Какие примеры доказывают полезность:", "- Проверки:", "- Инвариант тестов:"),
    ),
)
PR_CHECKLIST_HEADING = "## Технический чек-лист"

spec = importlib.util.spec_from_file_location("check_pr_governance", SCRIPT_PATH)
assert spec and spec.loader
check_pr_governance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_pr_governance)


def pr_event(*, title: str, body: str) -> dict:
    return {
        "pull_request": {
            "title": title,
            "body": body,
            "base": {"sha": "base"},
            "head": {"sha": "head"},
        }
    }


def valid_body() -> str:
    return """## Зачем

- Какую боль решает: закрывает repo gates для командных skills.
- Для кого: для авторов и ревьюеров.
- Когда не использовать: если изменение не касается командного skill или repo policy.
- Какие примеры доказывают полезность: локальный `python -m pytest`.

## Проверки

- [x] `python -m pytest` проходит.
"""


def description_format_body() -> str:
    return """## Проблема

- Какую боль решает: пустое поле границы проходило repo gates незамеченным.
- Для кого: для авторов и ревьюеров командных skills.

## Что изменилось

- Было: gate засчитывал соседнее поле как ответ.
- Стало: пустое поле останавливает PR.

## Границы

- Когда не использовать: если изменение не касается описания PR или repo policy.
- Что не меняется: проверка русского текста и приватных маркеров.

## Доказательства

- Какие примеры доказывают полезность: тело с пустым полем не проходит gate, заполненное проходит.
- Проверки: локальный `python -m pytest` проходит.
- Инвариант тестов: прежний инвариант сохранён, `false green` не стал проще, сценарий выполняется в CI.

## Технический чек-лист

- [x] `python -m pytest` проходит.
"""


def test_pr_title_and_body_must_be_russian() -> None:
    event = pr_event(title="Add governance gate", body=valid_body())
    errors = check_pr_governance.check_pr_metadata(event)
    assert any("PR title" in error and "русский" in error for error in errors)


def test_pr_body_must_fill_when_not_to_use() -> None:
    body = valid_body().replace(
        "- Когда не использовать: если изменение не касается командного skill или repo policy.",
        "- Когда не использовать:",
    )
    errors = check_pr_governance.check_pr_metadata(pr_event(title="Добавить repo gates", body=body))
    assert any("Когда не использовать" in error for error in errors)


def test_russian_pr_metadata_passes_with_allowed_technical_terms() -> None:
    errors = check_pr_governance.check_pr_metadata(pr_event(title="Добавить repo gates для team-ready skills", body=valid_body()))
    assert errors == []


def test_pull_request_template_does_not_introduce_forbidden_latin_words() -> None:
    template = PR_TEMPLATE_PATH.read_text(encoding="utf-8")
    assert check_pr_governance.latin_offenders(template) == []


def test_description_format_body_passes() -> None:
    errors = check_pr_governance.check_pr_metadata(
        pr_event(title="Ввести формат описания PR", body=description_format_body())
    )
    assert errors == []


def test_empty_when_not_to_use_does_not_borrow_neighbour_field() -> None:
    body = description_format_body().replace(
        "- Когда не использовать: если изменение не касается описания PR или repo policy.",
        "- Когда не использовать:",
    )
    assert "- Когда не использовать:\n- Что не меняется: проверка" in body
    errors = check_pr_governance.check_pr_metadata(pr_event(title="Ввести формат описания PR", body=body))
    assert any("Когда не использовать" in error for error in errors)


def test_unfilled_pull_request_template_fails_when_not_to_use_gate() -> None:
    template = PR_TEMPLATE_PATH.read_text(encoding="utf-8")
    assert check_pr_governance.extract_when_not_to_use(template) == ""
    errors = check_pr_governance.check_pr_metadata(pr_event(title="Ввести формат описания PR", body=template))
    assert any("Когда не использовать" in error for error in errors)


def test_pull_request_template_follows_description_contract() -> None:
    lines = [line for line in PR_TEMPLATE_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    form = [item for heading, fields in PR_DESCRIPTION_LAYOUT for item in (heading, *fields)]
    checklist_at = lines.index(PR_CHECKLIST_HEADING)
    assert lines[:checklist_at] == form

    checklist = lines[checklist_at + 1 :]
    assert checklist and all(line.startswith("- [ ] ") for line in checklist)
    assert any("`python -m pytest`" in line for line in checklist)
    assert any("Если менялись тесты" in line and "«Инвариант тестов»" in line for line in checklist)

    contributing = CONTRIBUTING_PATH.read_text(encoding="utf-8")
    canonical = contributing.split("\n## Описание PR\n", 1)[1].split("\n## ", 1)[0]
    for _heading, fields in PR_DESCRIPTION_LAYOUT:
        for field in fields:
            assert f"`{field.removeprefix('- ')}`" in canonical


FORK_SKILL_PATH = ROOT / "plugins/team-skills/skills/podacha-pravok-iz-forka/SKILL.md"


def test_fork_skill_teaches_canonical_pr_description() -> None:
    # Навык учит новичка. Своя копия шаблона с заголовком «Когда не применять»
    # уводила его на красный gate: `check_pr_governance.py` ищет поле дословно.
    skill = FORK_SKILL_PATH.read_text(encoding="utf-8")
    section = skill.split("## Шаблон PR Body", 1)[1]
    block = section.split("```markdown", 1)[1].split("```", 1)[0]
    lines = [line for line in block.splitlines() if line.strip()]
    assert lines == [item for heading, fields in PR_DESCRIPTION_LAYOUT for item in (heading, *fields)]
    assert "Когда не применять" not in skill
    assert check_pr_governance.extract_when_not_to_use(block) == ""
