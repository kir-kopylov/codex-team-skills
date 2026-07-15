from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins" / "team-skills" / "skills" / "add-team-skill" / "SKILL.md"


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
