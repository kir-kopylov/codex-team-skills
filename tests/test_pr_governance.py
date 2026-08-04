from __future__ import annotations

import importlib.util
from pathlib import Path

from conftest import ROOT


SCRIPT_PATH = ROOT / "scripts" / "check_pr_governance.py"
PR_TEMPLATE_PATH = ROOT / ".github" / "pull_request_template.md"

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


def test_non_pr_event_is_skipped_for_push_but_rejected_by_local_pr_gate() -> None:
    assert check_pr_governance.check_pr_metadata({}) == []

    errors = check_pr_governance.check_pr_metadata({}, require_pull_request=True)
    assert errors == ["event: отсутствует обязательный объект pull_request"]


def test_local_pr_gate_rejects_malformed_pull_request_payload(tmp_path: Path) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text('{"pull_request": null}', encoding="utf-8")

    exit_code = check_pr_governance.main(
        [
            "metadata",
            "--event-path",
            str(event_path),
            "--require-pull-request",
        ]
    )

    assert exit_code == 1


def test_pull_request_template_does_not_introduce_forbidden_latin_words() -> None:
    template = PR_TEMPLATE_PATH.read_text(encoding="utf-8")
    assert check_pr_governance.latin_offenders(template) == []
