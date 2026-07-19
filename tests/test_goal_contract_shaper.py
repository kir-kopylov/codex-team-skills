from __future__ import annotations

import yaml

from conftest import ROOT, load_registry


SKILL_DIR = ROOT / "plugins" / "team-skills" / "skills" / "goal-contract-shaper"


def test_goal_contract_shaper_keeps_universal_value_grammar() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    required_fragments = [
        "Универсальная Грамматика Деятельности",
        "Объект и ценность",
        "Финал и управление",
        "Роли",
        "Единицы процесса",
        "Человек внутри цикла",
        "Ожидание и зависание",
        "Стоимость и риск",
        "Журнал круга",
        "автономный агент там, где нужен человек",
    ]

    for fragment in required_fragments:
        assert fragment in content


def test_goal_contract_shaper_links_value_creation_example() -> None:
    registry = load_registry(SKILL_DIR)
    assert "examples/good-04-value-creation-cycle.md" in registry["example_files"]

    example = (SKILL_DIR / "examples" / "good-04-value-creation-cycle.md").read_text(
        encoding="utf-8"
    )
    assert "процесс создания ценности" in example
    assert "единицу потери" in example
    assert "сопровождаемый человеческий цикл" in example


def test_goal_contract_shaper_has_optional_runtime_handoff() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    reference = (SKILL_DIR / "references" / "runtime-handoff.md").read_text(
        encoding="utf-8"
    )

    for fragment in (
        "goalrt contract compile",
        "goalrt contract validate",
        "goalrt contract render-goal",
        "Не запускайте `goalrt run start`",
        "PARTIAL_ENFORCEMENT",
    ):
        assert fragment in content

    assert "Shaper не копирует schema" in reference
    assert "supervised" in reference


def test_goal_contract_shaper_registers_runtime_boundary_examples() -> None:
    registry = load_registry(SKILL_DIR)
    expected = {
        "examples/good-07-runtime-contract.md",
        "examples/good-08-runtime-missing-fallback.md",
        "examples/anti-07-unsupported-tools-enforced.md",
        "examples/anti-08-hard-token-budget.md",
    }

    assert expected <= set(registry["example_files"])


def test_goal_contract_shaper_preserves_full_contract_and_automatic_survey() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    registry = load_registry(SKILL_DIR)

    assert "После каждого ответа пользователя показывайте полный блок `Текущий контракт`" in content
    assert "не заменяйте его списком изменений, дельтой или краткой сводкой" in content
    assert "После каждого использования skill нужно запустить короткий опрос" in content
    assert "Что в этом использовании goal-contract-shaper было полезно?" in content
    assert "Что стоит доработать в skill или его формате?" in content
    assert "feedback_mode" not in content
    assert "feedback_mode" not in registry


def test_goal_contract_shaper_has_real_question_gate() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    assert "## Гейты Диалога" in content
    assert "### Настоящий Вопрос" in content
    assert "не менее двух разных допустимых вариантов" in content
    assert "только пользователь может сообщить необходимый факт, предпочтение или полномочие" in content
    assert "единственный допустимый вывод" in content
    assert "отрицательный ответ на который оставляет цель без жизнеспособного способа выполнения" in content


def test_goal_contract_shaper_checks_condition_compatibility() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    assert "### Совместимость Условий" in content
    assert "сравните его со всем принятым контрактом" in content
    assert "не принимайте новое условие" in content
    assert "Не храните два противоречащих условия как одновременно принятые" in content


def test_goal_contract_shaper_scopes_blocked() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    assert "`BLOCKED` всегда содержит область: `local` или `global`" in content
    assert "независимая работа продолжается" in content
    assert "оставить утверждение непринятым и продолжить остальные проверки" in content
    assert "`BLOCKED(scope=local)`" in content
    assert "`scope=global` допустим только при блокировке всей оставшейся работы" in content


def test_goal_contract_shaper_uses_checkpoint_tail_resume() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    assert "контрольная точка хранит последнее применённое событие или смещение" in content
    assert "читает только хвост журнала после неё" in content
    assert "явном аудите либо восстановлении после повреждения" in content
    assert "перед обычной записью запрещено перечитывать весь журнал" in content


def test_goal_contract_shaper_distinguishes_lifecycle_states() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    assert "утверждено (`APPROVED`)" in content
    assert "опубликовано (`PUBLISHED`)" in content
    assert "запущено (`STARTED`)" in content
    assert "| Файл | Назначение | Кто читает | Источник правды или проекция | Текущее состояние |" in content
    assert "Завершите одним следующим действием, его владельцем и ожидаемой проверкой" in content


def test_goal_contract_shaper_registers_new_regression_examples() -> None:
    registry = load_registry(SKILL_DIR)
    expected = {
        "examples/good-09-real-question-gate.md",
        "examples/anti-09-conflicting-conditions.md",
        "examples/good-10-local-blocked-progress.md",
        "examples/good-11-checkpoint-tail-resume.md",
        "examples/good-12-lifecycle-handoff.md",
    }

    assert expected <= set(registry["example_files"])
    for relative_path in expected:
        content = (SKILL_DIR / relative_path).read_text(encoding="utf-8")
        assert "## Вход" in content
        assert "## Ожидаемое Поведение" in content
        assert "## Нельзя" in content


def test_goal_contract_shaper_promotes_recent_known_exceptions() -> None:
    data = yaml.safe_load((SKILL_DIR / "known-exceptions.yaml").read_text(encoding="utf-8"))
    expected_sources = {
        "examples/good-09-real-question-gate.md",
        "examples/anti-09-conflicting-conditions.md",
        "examples/good-10-local-blocked-progress.md",
        "examples/good-11-checkpoint-tail-resume.md",
        "examples/good-12-lifecycle-handoff.md",
    }
    actual_sources = {item["source_example"] for item in data["exceptions"]}

    assert expected_sources <= actual_sources
    for item in data["exceptions"]:
        if item["source_example"] in expected_sources:
            assert (SKILL_DIR / item["source_example"]).is_file()
