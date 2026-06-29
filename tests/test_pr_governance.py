from __future__ import annotations

import importlib.util
from pathlib import Path

from conftest import ROOT


SCRIPT_PATH = ROOT / "scripts" / "check_pr_governance.py"

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


def hard_check_body() -> str:
    return valid_body() + """

## Жёсткая Проверка installer/release

- [x] Windows PowerShell 5.1 ValidateOnly проверен.
- [x] `manifest.json` и `latest.json` остаются валидными для release bundle.
- [x] Откат и повторная установка проверены через install/update path.
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


def test_protected_paths_require_hard_check_section() -> None:
    event = pr_event(title="Усилить release gate", body=valid_body())
    errors = check_pr_governance.check_protected_paths(event, ["installer/update-team-skills.sh"])
    assert any("защищённые installer/release пути" in error for error in errors)
    assert any("Жёсткая проверка installer/release" in error for error in errors)


def test_protected_paths_pass_with_hard_check_section() -> None:
    event = pr_event(title="Усилить release gate", body=hard_check_body())
    errors = check_pr_governance.check_protected_paths(event, ["scripts/build_release_bundle.py"])
    assert errors == []


def test_unprotected_paths_do_not_need_hard_check_section() -> None:
    event = pr_event(title="Обновить skill examples", body=valid_body())
    errors = check_pr_governance.check_protected_paths(event, ["plugins/team-skills/skills/verify/SKILL.md"])
    assert errors == []
