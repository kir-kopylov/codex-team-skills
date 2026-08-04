from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins" / "team-skills" / "skills" / "add-team-skill" / "SKILL.md"
REGISTRY = ROOT / "plugins" / "team-skills" / "skills" / "add-team-skill" / "skill.yaml"
CATALOG = ROOT / "catalog.md"
KNOWN_EXCEPTIONS = (
    ROOT / "plugins" / "team-skills" / "skills" / "add-team-skill" / "known-exceptions.yaml"
)
PROMOTION_EXAMPLE = (
    ROOT
    / "plugins"
    / "team-skills"
    / "skills"
    / "add-team-skill"
    / "examples"
    / "good-04-colleague-draft.md"
)


def test_add_team_skill_requires_automatic_review_convergence() -> None:
    content = SKILL.read_text(encoding="utf-8")

    for required in (
        "chatgpt-codex-connector",
        "conversation comments",
        "unresolved review threads",
        "без дополнительного запроса пользователя",
        "ответьте в треде",
        "последнего push повторно проверьте CI и review-треды",
        "обоснованные actionable comments исправлены",
    ):
        assert required in content


def test_add_team_skill_closes_personal_to_team_promotion() -> None:
    content = SKILL.read_text(encoding="utf-8")
    promotion_trigger = "перенеси мой личный skill в командную библиотеку"

    for required in (
        "канонический контейнер",
        "личным предшественником",
        "новой сессии",
        "явного разрешения пользователя",
        "subsystem-retirement-safeguard",
        "перенос не завершён",
        "постоянный scanner, updater, `doctor`",
    ):
        assert required in content

    assert promotion_trigger in content
    assert promotion_trigger in REGISTRY.read_text(encoding="utf-8")
    assert promotion_trigger in CATALOG.read_text(encoding="utf-8")

    exception = KNOWN_EXCEPTIONS.read_text(encoding="utf-8")
    assert "старая личная и новая командная версии" in exception
    assert "examples/good-04-colleague-draft.md" in exception

    example = PROMOTION_EXAMPLE.read_text(encoding="utf-8")
    assert "пакет в repo готов, а перенос в runtime ещё не завершён" in example
    assert "Нельзя автоматически удалять личного предшественника" in example
