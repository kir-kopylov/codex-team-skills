from __future__ import annotations

from conftest import ROOT, load_registry


SKILL = ROOT / "plugins" / "team-skills" / "skills" / "stuck-troubleshooting-reframe"


def test_plain_external_practice_request_does_not_trigger_reframe() -> None:
    body = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    registry = load_registry(SKILL)
    anti_example = (SKILL / "examples" / "anti-01.md").read_text(encoding="utf-8")

    assert "найди как люди решали похожую проблему" not in registry["natural_triggers"]
    assert "Одна просьба найти чужой опыт без repair-loop" in body
    assert "просьба найти похожие кейсы не открывает reframe" in body
    assert "reframe: not started" in anti_example
    assert "route: external-practice search" in anti_example


def test_external_candidate_is_only_an_input_to_local_gate() -> None:
    body = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    good_example = (SKILL / "examples" / "good-01.md").read_text(encoding="utf-8")

    for fragment in (
        "external_practice_candidate",
        "local_status` остаётся `NOT_TESTED",
        "не доказывает локальную причину",
        "не начинайте открытый веб-поиск внутри skill",
    ):
        assert fragment in body

    assert "`local_status: NOT_TESTED`" in good_example
    assert "`local_observable`" in good_example
