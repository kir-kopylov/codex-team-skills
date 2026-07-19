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
        "эксплуатационным контуром",
        "из доступных доказательств",
        "authoritative repo",
        "пометь классификацию как гипотезу",
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
    assert "Ограничение относится к forensic-результату, а не ко всему сообщению" in response_contract


def test_full_template_carries_scope_category_into_the_final_rebuild() -> None:
    content = SKILL_PATH.read_text(encoding="utf-8")
    response_contract = section(content, "## Обязательная Структура Ответа")

    measure_contract = "- [конкретная мера] — [обязательно / только при дополнительных условиях / вне scope]"
    assert "Меры:" in response_contract
    assert measure_contract in response_contract
    assert response_contract.index("Как делают сильные команды:") < response_contract.index("Меры:")
    assert "`Итоговая пересборка`" in response_contract
    assert "одного-трёх проверяемых направлений" in response_contract
    assert "только меры категории `обязательно`" in response_contract


def test_regression_examples_are_registered() -> None:
    registry = load_registry(SKILL_DIR)
    expected = {
        "examples/good-04-proportional-team-skills-remediation.md",
        "examples/good-05-managed-fleet-justifies-platform.md",
        "examples/anti-03-full-template-after-format-limit.md",
    }

    assert expected <= set(registry["example_files"])


def test_simple_team_skills_case_keeps_required_work_without_a_platform() -> None:
    content = read_example("good-04-proportional-team-skills-remediation.md")
    expected = section(content, "## Ожидаемое Поведение")
    forbidden = section(content, "## Нельзя")

    for phrase in [
        "штатные команды Codex marketplace",
        "agent-guided переход",
        "Windows/macOS smoke",
        "установки, переустановки, обновления и удаления",
    ]:
        assert phrase in expected
    assert "MDM, KMS и production telemetry относятся к `только при дополнительных условиях`" in expected
    assert "Отдельные пользовательские update, status и repair-команды" in expected
    assert "новая update-платформа относятся к `вне scope`" in expected
    assert "RepairInstall" not in content
    for retired_phrase in [
        "signed one-shot Windows installer",
        "Windows PowerShell 5.1",
        "повторную установку через временную копию",
        "автоматический rollback при ошибке замены",
    ]:
        assert retired_phrase not in content
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
    input_section = section(content, "## Вход")
    expected = section(content, "## Ожидаемое Поведение")
    forbidden = section(content, "## Нельзя")

    assert "Сам forensic-результат" in input_section
    assert "repo-опрос вынеси отдельно" in input_section
    assert "ровно одним предложением" in expected
    assert "к forensic-результату, а не ко всему сообщению" in expected
    assert "отдельным стандартным блоком" in expected
    assert "полный forensic-шаблон" in forbidden
    assert "поля для каждого тезиса" in forbidden


def test_known_exception_captures_audit_and_remediation_scope_confusion() -> None:
    data = yaml.safe_load((SKILL_DIR / "known-exceptions.yaml").read_text(encoding="utf-8"))
    exceptions = data["exceptions"]

    matches = [item for item in exceptions if "Audit scope" in item["root_cause"]]
    assert matches, "Нет regression-карточки о смешении audit scope и remediation scope"
    item = matches[0]
    assert "корпоративной платформы" in item["symptom"]
    assert "Audit scope" in item["root_cause"]
    assert "remediation scope" in item["root_cause"]
    assert "текущую delivery-модель" in item["root_cause"]
    assert "не более трёх обязательных направлений" in item["do_next_time"]
    assert item["source_example"] == "examples/good-04-proportional-team-skills-remediation.md"
