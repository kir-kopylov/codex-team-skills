from __future__ import annotations

from conftest import ROOT, skill_dirs


REQUIRED_SECTIONS = (
    "# Domain Playbook",
    "## Что Нельзя Потерять",
    "## Что Надо Обезличить",
    "## Interface Mechanics",
    "## Recovery And Edge Cases",
)


def test_domain_playbooks_have_minimum_sections() -> None:
    for skill_dir in skill_dirs():
        playbook = skill_dir / "references" / "domain-playbook.md"
        if not playbook.exists():
            continue

        content = playbook.read_text(encoding="utf-8")
        for section in REQUIRED_SECTIONS:
            assert section in content, f"{playbook} missing {section}"


def test_marketplace_background_listing_assistant_has_olx_acceptance_playbook() -> None:
    playbook = (
        ROOT
        / "plugins"
        / "team-skills"
        / "skills"
        / "marketplace-background-listing-assistant"
        / "references"
        / "domain-playbook.md"
    )
    assert playbook.exists(), "OLX acceptance skill должен иметь domain-playbook.md"

    content = playbook.read_text(encoding="utf-8")
    for expected in (
        "/adding/",
        "/myaccount/",
        "input[type=file][data-testid=\"attach-photos-input\"]",
        "Не рекламировать",
        "coverage by physical item",
        "тегін",
        "сыйға",
        "алып кету",
    ):
        assert expected in content


def test_marketplace_listing_launch_notice_cannot_replace_inventory() -> None:
    skill = (
        ROOT
        / "plugins"
        / "team-skills"
        / "skills"
        / "marketplace-background-listing-assistant"
        / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert "Не завершайте первый ответ уведомлением" in skill
    assert "Сразу начните доступную read-only инвентаризацию" in skill
    assert "задайте один ближайший вопрос" in skill
