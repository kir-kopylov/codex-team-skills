from __future__ import annotations

import yaml

from conftest import ROOT, load_registry


SKILL = ROOT / "plugins" / "team-skills" / "skills" / "resume-interrupted-goal"


def test_resume_skill_keeps_read_only_reconstruction_contract() -> None:
    content = (SKILL / "SKILL.md").read_text(encoding="utf-8")

    for required in (
        "Выполните один проход только для чтения",
        "Память чата используйте только как указатель",
        "Текущий provider state доказывает push, PR/MR, review, merge",
        "Перед повтором commit, push, PR/MR, сообщения, запроса",
        "Разведите четыре независимых состояния",
        "Сам шаг не выполняйте",
        "Изменения: нет",
    ):
        assert required in content


def test_resume_skill_uses_checkpoint_and_tail_without_full_replay() -> None:
    content = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    reference = (SKILL / "references" / "state-model.md").read_text(encoding="utf-8")

    assert "прочитайте только события после курсора" in content
    assert "Не читайте весь append-only журнал при каждом цикле" in content
    assert "отсутствии контрольной точки" in content
    assert "явному запросу на аудит или восстановление" in content
    assert "Обычное возобновление читает контрольную точку и только события после cursor" in reference


def test_resume_skill_has_fail_closed_verdicts() -> None:
    content = (SKILL / "SKILL.md").read_text(encoding="utf-8")

    for verdict in (
        "RESUME_SAFE",
        "RECONCILE_REQUIRED",
        "NO_ACTIVE_GOAL",
        "AMBIGUOUS_TARGET",
        "INSUFFICIENT_EVIDENCE",
    ):
        assert verdict in content

    assert "route говорит «первый цикл не запущен»" in content
    assert "state говорит `ACTIVE_REVIEW_PENDING`" in content
    assert "выбирайте `RECONCILE_REQUIRED`" in content


def test_resume_skill_keeps_neighbor_ownership_boundaries() -> None:
    content = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    registry = load_registry(SKILL)

    assert "codex-session-to-repo-rescue" in content
    assert "goal-contract-shaper" in content
    assert "git-worktree-reality-check" in content
    assert "`goalrt run start`, `goalrt run recover`" in content
    assert "Не выполняйте его внутри этого skill" in content
    assert registry["status"] == "experimental"
    assert registry["owner"] == "@kir-kopylov"


def test_resume_skill_does_not_ship_second_runtime_or_parser() -> None:
    scripts = {path.name for path in (SKILL / "scripts").iterdir() if path.is_file()}
    content = (SKILL / "SKILL.md").read_text(encoding="utf-8")

    assert scripts == {"log_usage_feedback.py"}
    assert "Не создавайте новый runtime, parser, журнал или собственную схему состояния" in content
    assert "Не разбирайте неизвестную схему самостоятельно" in content
    assert "полного чтения raw session" in content


def test_resume_skill_registers_boundary_examples() -> None:
    registry = load_registry(SKILL)
    expected = {
        "examples/good-01.md": "RESUME_SAFE",
        "examples/good-02.md": "RECONCILE_REQUIRED",
        "examples/good-03.md": "INSUFFICIENT_EVIDENCE",
        "examples/anti-01.md": "AMBIGUOUS_TARGET",
        "examples/anti-02.md": "read-only",
    }

    assert set(registry["example_files"]) == set(expected)
    for relative_path, phrase in expected.items():
        example = (SKILL / relative_path).read_text(encoding="utf-8")
        assert phrase in example
        assert "## Вход" in example
        assert "## Ожидаемое Поведение" in example
        assert "## Нельзя" in example


def test_resume_skill_keeps_mandatory_automatic_survey() -> None:
    content = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    registry = load_registry(SKILL)

    assert "После каждого использования skill нужно запустить короткий опрос" in content
    assert "Что в этом использовании resume-interrupted-goal было полезно?" in content
    assert "Что стоит доработать в skill или его формате?" in content
    assert "обязательный post-use блок" in content
    assert 'написать "пропустить"' in content
    assert "feedback_mode" not in content
    assert "feedback_mode" not in registry


def test_resume_skill_known_exceptions_point_to_existing_examples() -> None:
    data = yaml.safe_load((SKILL / "known-exceptions.yaml").read_text(encoding="utf-8"))

    assert len(data["exceptions"]) >= 4
    for item in data["exceptions"]:
        assert (SKILL / item["source_example"]).is_file()


def test_resume_skill_has_openai_interface_metadata() -> None:
    data = yaml.safe_load((SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8"))
    interface = data["interface"]

    assert interface["display_name"] == "Возобновить прерванный /goal"
    assert interface["short_description"]
    assert "$resume-interrupted-goal" in interface["default_prompt"]
