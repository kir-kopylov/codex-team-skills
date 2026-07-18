from __future__ import annotations

import yaml

from conftest import ROOT, load_registry


SKILL_DIR = ROOT / "plugins" / "team-skills" / "skills" / "production-forensic-auditor"
SKILL_PATH = SKILL_DIR / "SKILL.md"


def read_example(name: str) -> str:
    return (SKILL_DIR / "examples" / name).read_text(encoding="utf-8")


def section(content: str, heading: str) -> str:
    start = content.index(heading) + len(heading)
    remainder = content[start:]
    return remainder.split("\n## ", 1)[0]


def test_skill_defines_a_proportional_remediation_boundary() -> None:
    content = SKILL_PATH.read_text(encoding="utf-8")
    remediation = section(content, "## Граница Remediation Scope")

    required = [
        "буквальную цель",
        "класс продукта",
        "Не повышай и не понижай класс продукта",
        "`обязательно`",
        "`только при дополнительных условиях`",
        "`вне scope`",
        "не более чем в три проверяемых направления",
        "Ширина forensic-аудита не расширяет remediation scope",
        "релевантны исходному тексту, продукту и запросу",
    ]
    for phrase in required:
        assert phrase in remediation


def test_explicit_format_limit_overrides_the_full_template() -> None:
    content = SKILL_PATH.read_text(encoding="utf-8")
    response_contract = section(content, "## Обязательная Структура Ответа")

    for phrase in ["«только X»", "«одним предложением»", "«и всё»", "ровно одно предложение"]:
        assert phrase in response_contract
    assert "repo-опрос" in response_contract
    assert "отдельным стандартным блоком" in response_contract
    assert "считается завершённым forensic-разбором" in response_contract


def test_regression_examples_are_registered() -> None:
    registry = load_registry(SKILL_DIR)
    expected = {
        "examples/good-04-proportional-team-skills-remediation.md",
        "examples/good-05-managed-fleet-justifies-platform.md",
        "examples/anti-03-full-template-after-format-limit.md",
    }

    assert expected <= set(registry["example_files"])
    assert registry["last_reviewed"] == "2026-07-18"


def test_simple_team_skills_case_keeps_required_work_without_a_platform() -> None:
    content = read_example("good-04-proportional-team-skills-remediation.md")
    expected = section(content, "## Ожидаемое Поведение")
    forbidden = section(content, "## Нельзя")

    for phrase in ["Windows update", "PS5.1 signature", "`RepairInstall`", "Windows tests"]:
        assert phrase in expected
    assert "MDM, KMS и production telemetry относятся к `только при дополнительных условиях`" in expected
    assert "новая update-платформа относятся к `вне scope`" in expected
    for addition in ["MDM", "KMS", "telemetry", "новую платформу обновлений"]:
        assert addition in forbidden


def test_managed_fleet_case_preserves_its_explicit_operational_requirements() -> None:
    content = read_example("good-05-managed-fleet-justifies-platform.md")
    input_section = section(content, "## Вход")
    expected = section(content, "## Ожидаемое Поведение")

    for condition in ["inventory", "SLO", "remote recovery", "audit trail"]:
        assert condition in input_section
    assert "Тяжёлая архитектура допустима именно из-за входных условий" in expected
    for safeguard in ["staged rollout", "remote recovery", "ротация ключей", "audit trail", "rollback"]:
        assert safeguard in expected


def test_one_sentence_case_forbids_the_full_template_but_keeps_the_survey() -> None:
    content = read_example("anti-03-full-template-after-format-limit.md")
    expected = section(content, "## Ожидаемое Поведение")
    forbidden = section(content, "## Нельзя")

    assert "ровно одним предложением" in expected
    assert "отдельным стандартным блоком" in expected
    assert "полный forensic-шаблон" in forbidden
    assert "шесть полей" in forbidden


def test_standard_survey_contract_is_unchanged() -> None:
    content = SKILL_PATH.read_text(encoding="utf-8")
    survey_at = content.index("## Опрос После Использования")
    logging_at = content.index("## Логирование Сбоев")
    survey = content[survey_at:logging_at]

    assert survey_at < logging_at
    assert "1. Что в этом использовании production-forensic-auditor было полезно?" in survey
    assert "2. Что стоит доработать в skill или его формате?" in survey
    assert 'написать "пропустить"' in survey


def test_known_exception_captures_audit_and_remediation_scope_confusion() -> None:
    data = yaml.safe_load((SKILL_DIR / "known-exceptions.yaml").read_text(encoding="utf-8"))
    exceptions = data["exceptions"]

    matches = [item for item in exceptions if "Audit scope" in item["root_cause"]]
    assert matches, "Нет regression-карточки о смешении audit scope и remediation scope"
    item = matches[0]
    assert "корпоративной платформы" in item["symptom"]
    assert "Audit scope" in item["root_cause"]
    assert "remediation scope" in item["root_cause"]
    assert "не более трёх обязательных направлений" in item["do_next_time"]
    assert "Обезличенный случай" in item["source_example"]
