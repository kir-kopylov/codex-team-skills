from __future__ import annotations

from conftest import ROOT


SKILL_DIR = ROOT / "plugins" / "team-skills" / "skills" / "browser-preflight"


def test_browser_preflight_observes_available_state_before_human_handoff() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    example = (SKILL_DIR / "examples" / "good-01-full-preflight.md").read_text(
        encoding="utf-8"
    )

    for required in (
        "## Гейт Перед Вовлечением Человека",
        "внутренним браузером или `Chrome control`",
        "`computer-use`",
        "DOM, Playwright, журналы или `check_grants.py`",
        "Только после фактически наблюдавшегося барьера",
        "одно минимальное действие",
    ):
        assert required in content

    assert "Пользователь не получает просьбу открыть страницу или пересказать список" in example
    assert "Пользователь не подтверждает состояние, доступное агенту" in example


def test_browser_preflight_does_not_assume_application_windows_are_invisible() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    examples = "\n".join(
        path.read_text(encoding="utf-8") for path in (SKILL_DIR / "examples").glob("*.md")
    )

    for forbidden in (
        "агент её не видит и НЕ вправе",
        "ассистент его не видит",
        "после каждого домена агент спрашивает человека",
    ):
        assert forbidden not in content + examples
