from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "plugins" / "team-skills" / "skills" / "chat-to-skill-miner"


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def test_chat_to_skill_miner_has_a_narrow_pipeline_boundary() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    assert "ранжированный список" in text
    assert "skill-methodologist" in text
    assert "razbor-chata-na-artefakty" in text
    assert "Не запускайте его по умолчанию" in text
    assert "не проектируйте полный workflow" in text
    assert "MacBook" not in text


def test_chat_to_skill_miner_template_stops_before_contract_design() -> None:
    template = (SKILL_DIR / "references" / "output-template.md").read_text(
        encoding="utf-8"
    )

    assert "## Передача После Выбора" in template
    assert "skill-methodologist" in template
    assert "Полный контракт" in template
    assert "признаки проверяемости" in template
    assert "Implementation-Ready" not in template


def test_chat_to_skill_miner_is_team_ready_and_has_six_examples() -> None:
    registry = yaml.safe_load((SKILL_DIR / "skill.yaml").read_text(encoding="utf-8"))

    assert registry["status"] == "team-ready"
    assert len(registry["example_files"]) == 6
    assert registry["last_reviewed"] == "2026-08-24"
    for relative_path in registry["example_files"]:
        assert (SKILL_DIR / relative_path).is_file()


def test_chat_to_skill_miner_compares_candidates_with_existing_library() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    template = (SKILL_DIR / "references" / "output-template.md").read_text(
        encoding="utf-8"
    )
    example = (SKILL_DIR / "examples" / "good-03.md").read_text(
        encoding="utf-8"
    )

    verdicts = (
        "`new skill`",
        "`patch existing skill`",
        "`shared reference/test`",
        "`no library change`",
    )
    for verdict in verdicts:
        assert verdict in text
        assert verdict in template

    for field in (
        "существующий ближайший skill",
        "поведенческая дельта",
        "вердикт относительно библиотеки",
    ):
        assert field in template

    assert "с теми же входом, результатом и точкой остановки" in text
    assert "не превращаются в три новых skills" in example


def test_chat_to_skill_miner_checks_delivery_state_before_ranking() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    reference = (SKILL_DIR / "references" / "implementation-state.md").read_text(
        encoding="utf-8"
    )
    template = (SKILL_DIR / "references" / "output-template.md").read_text(
        encoding="utf-8"
    )

    fields = ("implementation_state", "delta_match", "runtime_state")
    implementation_states = (
        "PROPOSED_ONLY",
        "WORKTREE_ONLY",
        "COMMITTED",
        "PR_OPEN",
        "MERGED",
        "UNKNOWN",
    )
    delta_matches = ("EXACT", "PARTIAL", "NONE", "UNKNOWN")
    runtime_states = ("INSTALLED", "NOT_INSTALLED", "UNKNOWN")

    for token in (*fields, *implementation_states, *delta_matches, *runtime_states):
        assert token in reference
        assert token in template

    delta_position = text.index("сформулируйте точную поведенческую дельту")
    state_position = text.index("`implementation_state`")
    assert delta_position < state_position
    assert "MERGED + EXACT" in text
    assert "раздел «Уже реализуется»" in text
    assert "только ещё не реализованный кандидат или его остаточную дельту" in text


def test_implementation_state_gate_keeps_repo_and_runtime_evidence_separate() -> None:
    reference = (SKILL_DIR / "references" / "implementation-state.md").read_text(
        encoding="utf-8"
    )
    known_exceptions = yaml.safe_load(
        (SKILL_DIR / "known-exceptions.yaml").read_text(encoding="utf-8")
    )["exceptions"]

    normalized_reference = _normalize_whitespace(reference)
    assert "устаревший локальный `main` для этого недостаточен" in normalized_reference
    assert "ставьте `UNKNOWN`, а не `PROPOSED_ONLY`" in normalized_reference
    assert "`MERGED` не доказывает `INSTALLED`" in normalized_reference
    assert "`INSTALLED` не доказывает активность текущей сессии" in normalized_reference
    assert (
        "Не запускайте install, update, checkout, reset, stash, commit"
        in normalized_reference
    )
    assert any(
        "снова попадает в рекомендацию V1" in item["symptom"]
        and item["source_example"] == "examples/good-04.md"
        for item in known_exceptions
    )


def test_chat_to_skill_miner_example_and_ui_prompt_exclude_delivered_work() -> None:
    example = (SKILL_DIR / "examples" / "good-04.md").read_text(encoding="utf-8")
    agent = yaml.safe_load(
        (SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8")
    )["interface"]

    normalized_example = _normalize_whitespace(example)
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "`MERGED + EXACT` получает `no library change`" in normalized_example
    assert "часть с `PR_OPEN` сразу переносится в «Уже реализуется»" in normalized_example
    assert "остаток становится новой самостоятельной дельтой" in normalized_example
    assert "дайте доказанный статус доступной дельты либо `UNKNOWN`" in skill
    assert "не завершайте ход строкой запуска" in skill
    assert "первый ход заканчивается доказанным `UNKNOWN`" in normalized_example
    assert "уже реализованное от предложенного" in agent["short_description"]
    assert "уже реализованное от предложенного" in agent["default_prompt"]
    assert len(agent["default_prompt"]) <= 128


def test_partial_residual_is_reclassified_until_terminal_state() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    reference = (SKILL_DIR / "references" / "implementation-state.md").read_text(
        encoding="utf-8"
    )
    template = (SKILL_DIR / "references" / "output-template.md").read_text(
        encoding="utf-8"
    )
    example = (SKILL_DIR / "examples" / "good-04.md").read_text(encoding="utf-8")

    normalized_text = _normalize_whitespace(text)
    normalized_reference = _normalize_whitespace(reference)
    normalized_template = _normalize_whitespace(template)
    normalized_example = _normalize_whitespace(example)

    assert "остаток сформулируйте как новую самостоятельную дельту" in normalized_text
    assert "повторите для него read-only гейт с шага 7" in normalized_text
    assert "только после собственной классификации `PROPOSED_ONLY + NONE`" in normalized_text
    assert "прежний остаток повторился" in normalized_text
    assert "Не наследуйте для него состояние" in normalized_reference
    assert "Повторяйте шаги 1–5 для каждого следующего `PARTIAL`" in normalized_reference
    assert "прогресса нет" in normalized_reference
    assert "состояние родительской дельты не наследуется" in normalized_template
    assert "итерация `PARTIAL` не уменьшила остаток или повторила его" in normalized_template
    assert "остаток становится новой самостоятельной дельтой" in normalized_example
    assert "только независимый `PROPOSED_ONLY + NONE` допускает остаток в V1" in normalized_example
    assert "`implementation_state: UNKNOWN`" in normalized_example
    assert "`delta_match: UNKNOWN`" in normalized_example


def test_composite_delta_is_not_collapsed_across_delivery_layers() -> None:
    text = _normalize_whitespace(
        (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    )
    reference = _normalize_whitespace(
        (SKILL_DIR / "references" / "implementation-state.md").read_text(
            encoding="utf-8"
        )
    )
    template = _normalize_whitespace(
        (SKILL_DIR / "references" / "output-template.md").read_text(
            encoding="utf-8"
        )
    )
    example = _normalize_whitespace(
        (SKILL_DIR / "examples" / "good-04.md").read_text(encoding="utf-8")
    )

    assert "не объединяйте признаки из `main`, PR, commit и worktree" in text
    assert "`MERGED + EXACT` означает `no library change` только когда" in text
    assert "Считайте `delta_match` отдельно на каждом целостном снимке слоя" in reference
    assert "не сворачивайте составную дельту в самый дальний слой" in reference.lower()
    assert "не объединяйте признаки разных слоёв в один `delta_match`" in template
    assert "не собирает ложный `MERGED + EXACT`" in example


def test_committed_state_requires_the_current_active_tip_snapshot() -> None:
    skill = _normalize_whitespace(
        (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    )
    reference_raw = (SKILL_DIR / "references" / "implementation-state.md").read_text(
        encoding="utf-8"
    )
    reference = _normalize_whitespace(reference_raw)
    template = _normalize_whitespace(
        (SKILL_DIR / "references" / "output-template.md").read_text(
            encoding="utf-8"
        )
    )
    example = _normalize_whitespace(
        (SKILL_DIR / "examples" / "good-04.md").read_text(encoding="utf-8")
    )
    registry = yaml.safe_load((SKILL_DIR / "skill.yaml").read_text(encoding="utf-8"))
    known_exceptions = yaml.safe_load(
        (SKILL_DIR / "known-exceptions.yaml").read_text(encoding="utf-8")
    )["exceptions"]

    state_section = reference_raw.split("`delta_match`", maxsplit=1)[0]
    assert [
        line.split("`")[1]
        for line in state_section.splitlines()
        if line.startswith("- `")
    ] == [
        "PROPOSED_ONLY",
        "WORKTREE_ONLY",
        "COMMITTED",
        "PR_OPEN",
        "MERGED",
        "UNKNOWN",
    ]
    assert "Для `COMMITTED` недостаточно найти исторический commit" in skill
    assert "реализующий commit достижим из этого tip" in reference
    assert "итоговый снимок tip сам содержит всю дельту" in reference
    assert "head закрытого незамерженного pr" in reference.lower()
    assert "исторический commit и закрытый незамерженный PR" in template
    assert "`COMMITTED + EXACT` запрещён" in example
    assert "tip активной ветки доставки" in registry["use_cases"][-1]
    assert any(
        "исторический, отменённый commit" in item["symptom"]
        and "достижимость реализующего commit" in item["do_next_time"]
        for item in known_exceptions
    )


def test_chat_to_skill_miner_scoring_thresholds_are_unchanged() -> None:
    scoring = (SKILL_DIR / "references" / "scoring.md").read_text(encoding="utf-8")

    assert "Высокий: 15 баллов и выше" in scoring
    assert "Средний: 10–14 баллов" in scoring
    assert "Низкий: меньше 10 баллов" in scoring
