from __future__ import annotations

from conftest import ROOT, load_registry


SKILL = ROOT / "plugins" / "team-skills" / "skills" / "sverka-zapuskov-pri-rashozhdenii"
PROBE = ROOT / "plugins" / "team-skills" / "skills" / "proverka-prichin-sboya"


def test_skill_declares_retrospective_evidence_contract() -> None:
    body = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    registry = load_registry(SKILL)

    assert registry["status"] == "experimental"
    assert registry["owner"] == "@kir-kopylov"
    assert len(registry["example_files"]) == 5

    for fragment in (
        "эффективный вход каждого запуска",
        "`совпадает`, `различается` или `неизвестно`",
        "`ПОДТВЕРЖДЕНА`",
        "`ОПРОВЕРГНУТА`",
        "`НЕ УСТАНОВЛЕНА`",
        "официальная документация — доступную возможность, но не её использование",
        "текущий повтор — нынешнее поведение, но не прошлое состояние",
        "Изменившийся фактор доказывает несопоставимость запусков",
    ):
        assert fragment in body


def test_examples_cover_changed_prompt_time_tools_and_missing_history() -> None:
    changed_prompt = (
        SKILL / "examples" / "good-01-izmenilsya-zapros.md"
    ).read_text(encoding="utf-8")
    changed_time = (SKILL / "examples" / "good-02-izmenilos-vremya.md").read_text(
        encoding="utf-8"
    )
    changed_tools = (
        SKILL / "examples" / "good-03-raznye-instrumenty.md"
    ).read_text(encoding="utf-8")
    missing_history = (
        SKILL / "examples" / "anti-02-net-istorii-zapuskov.md"
    ).read_text(encoding="utf-8")
    general_reference = (
        SKILL / "examples" / "anti-01-spravka-o-rezhimah.md"
    ).read_text(encoding="utf-8")

    assert "найди новые" in changed_prompt
    assert "`ОПРОВЕРГНУТА`" in changed_prompt
    assert "`НЕ УСТАНОВЛЕНА`" in changed_prompt
    assert "интервалом в неделю" in changed_time
    assert "нынешнего состояния" in changed_time
    assert "первый запуск вызвал веб-поиск, второй ответил без него" in changed_tools
    assert "`ПОДТВЕРЖДЕНА`" in changed_tools
    assert "Причину пометить `НЕ УСТАНОВЛЕНА`" in missing_history
    assert "один минимальный артефакт" in missing_history
    assert "Конкретных запусков, результатов и причинного вопроса нет" in general_reference
    assert "Не запускать причинную сверку" in general_reference


def test_prospective_probe_routes_completed_run_comparison_to_new_skill() -> None:
    body = (PROBE / "SKILL.md").read_text(encoding="utf-8")
    registry = load_registry(PROBE)

    assert "два уже завершённых запуска" in body
    assert "`sverka-zapuskov-pri-rashozhdenii`" in body
    launch = body.split("## Запуск Навыка", 1)[1].split("\n## ", 1)[0]
    assert "не объявляйте этот" in launch
    assert "прямо назовите `sverka-zapuskov-pri-rashozhdenii`" in launch
    assert "Не собирайте входы ретроспективной сверки" in launch
    assert launch.index("sverka-zapuskov-pri-rashozhdenii") < launch.index(
        "Применяю экспериментальный навык"
    )
    assert any(
        "sverka-zapuskov-pri-rashozhdenii" in boundary
        for boundary in registry["do_not_use_for"]
    )
