"""Проверки структуры пакета, не семантическая оценка ответов модели.

Подстрока не различает утверждение и его отрицание. Причинные выводы и
направление передачи задачи проверяются отдельными независимыми пробами по
references/behavior-probe-batch.md навыка dobavlenie-navyka-v-biblioteku.
"""

from __future__ import annotations

from conftest import ROOT, load_registry


SKILL = ROOT / "plugins" / "team-skills" / "skills" / "sverka-zapuskov-pri-rashozhdenii"
PROBE = ROOT / "plugins" / "team-skills" / "skills" / "proverka-prichin-sboya"


def test_registry_keeps_the_reviewed_example_set() -> None:
    registry = load_registry(SKILL)
    expected = {
        "examples/good-01-izmenilsya-zapros.md",
        "examples/good-02-izmenilos-vremya.md",
        "examples/good-03-raznye-instrumenty.md",
        "examples/anti-01-spravka-o-rezhimah.md",
        "examples/anti-02-net-istorii-zapuskov.md",
    }

    assert registry["status"] == "experimental"
    assert registry["owner"] == "@kir-kopylov"
    assert set(registry["example_files"]) == expected
    assert len(registry["example_files"]) == len(expected)
    for relative in expected:
        assert (SKILL / relative).is_file()


def test_documentation_lists_public_verdict_tokens() -> None:
    body = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    for token in (
        "совпадает", "различается", "неизвестно",
        "ПОДТВЕРЖДЕНА", "ОПРОВЕРГНУТА", "НЕ УСТАНОВЛЕНА",
    ):
        assert f"`{token}`" in body


def test_both_routing_targets_exist_and_are_named_in_boundaries() -> None:
    for source, target in ((SKILL, PROBE), (PROBE, SKILL)):
        assert (target / "SKILL.md").is_file()
        body = (source / "SKILL.md").read_text(encoding="utf-8")
        assert f"`{target.name}`" in body
        assert any(
            target.name in boundary
            for boundary in load_registry(source)["do_not_use_for"]
        )
