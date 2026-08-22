from __future__ import annotations

from conftest import ROOT


SKILL = (
    ROOT
    / "plugins"
    / "team-skills"
    / "skills"
    / "peredelka-dogovorov-arendy"
    / "SKILL.md"
)


def test_launch_notice_cannot_replace_document_discovery() -> None:
    content = SKILL.read_text(encoding="utf-8")

    assert "Не завершайте первый ответ планом будущей разведки" in content
    assert "сразу выполните read-only поиск документов" in content
    assert "задайте один ближайший вопрос о папке или исходном договоре" in content


def test_requested_drafts_do_not_require_repeated_plan_confirmation() -> None:
    content = SKILL.read_text(encoding="utf-8")

    assert "продолжайте к черновикам без\nповторного подтверждения" in content
    assert "не превращайте показ плана в\n  повторный запрос уже данного разрешения" in content
    assert "Не начинайте делать документы без подтверждения" not in content
