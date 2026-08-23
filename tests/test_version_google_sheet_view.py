from __future__ import annotations

from conftest import ROOT


SKILL = (
    ROOT
    / "plugins"
    / "team-skills"
    / "skills"
    / "version-google-sheet-view"
    / "SKILL.md"
)


def test_launch_notice_cannot_replace_sheet_and_repo_discovery() -> None:
    content = SKILL.read_text(encoding="utf-8")

    assert "Не завершайте первый ответ уведомлением или планом" in content
    assert "самостоятельно проверьте доступный контекст Google Sheets" in content
    assert "read-only состояние репозитория" in content
    assert "задайте один ближайший вопрос" in content
    assert "к пути YAML переходите только после определения источника" in content
