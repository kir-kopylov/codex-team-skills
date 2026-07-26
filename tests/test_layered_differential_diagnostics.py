from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys

from conftest import ROOT, load_registry


SKILL = ROOT / "plugins" / "team-skills" / "skills" / "layered-differential-diagnostics"
STUCK = ROOT / "plugins" / "team-skills" / "skills" / "stuck-troubleshooting-reframe"
VALIDATOR = SKILL / "scripts" / "validate_diagnostic_ledger.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_diagnostic_ledger", VALIDATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _valid_entry() -> dict:
    return {
        "outcome": "Пользователь видит свежий результат операции",
        "observed_facts": [
            {
                "fact": "Клиент отправил запрос, но целевой результат не появился",
                "source": "санированный журнал",
                "observed_at": "2026-07-27T10:00:00Z",
            }
        ],
        "state_fingerprint": {
            "target": "synthetic-service",
            "version": "v1",
            "environment": "test",
        },
        "causal_boundaries": ["клиент", "интеграция", "внешняя зависимость"],
        "hypothesis_a": "Клиент не передаёт запрос интеграции",
        "hypothesis_b": "Интеграция передаёт запрос, но не получает ответ",
        "causal_contrast": "Наличие исходящего запроса на границе интеграции",
        "held_constant": ["версия", "конфигурация", "маршрут"],
        "probe": "Проверить один запрос в журнале границы интеграции",
        "owner": "assistant",
        "expected_if_a": "Исходящий запрос отсутствует",
        "expected_if_b": "Исходящий запрос присутствует, ответ отсутствует",
        "evidence_to_capture": "Одна санированная запись с временем",
        "safety_gate": "Только чтение существующего журнала",
        "stop_condition": "Остановиться после одного запроса",
        "verdict": "inconclusive",
    }


def test_skill_declares_first_failure_differential_contract() -> None:
    body = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    registry = load_registry(SKILL)

    assert registry["status"] == "experimental"
    assert registry["owner"] == "@kir-kopylov"

    for fragment in (
        "при первом неоднозначном сбое",
        "один `causal_contrast`",
        "hypothesis_a",
        "hypothesis_b",
        "expected_if_a",
        "expected_if_b",
        "outcome_reached",
        "favors_a",
        "favors_b",
        "inconclusive",
        "invalid_test",
        "blocked",
        "stuck-troubleshooting-reframe",
        "Не создавайте эти файлы без согласия",
        "scripts/validate_diagnostic_ledger.py",
    ):
        assert fragment in body


def test_skill_separates_safe_checks_from_permissioned_changes() -> None:
    body = (SKILL / "SKILL.md").read_text(encoding="utf-8")

    for safe_fragment in (
        "чтение конфигурации",
        "просмотр процессов",
        "разбор уже полученных артефактов",
        "временные локальные пробы",
    ):
        assert safe_fragment in body

    for permissioned_fragment in (
        "запись конфигурации",
        "перезапуск сервиса",
        "переключение VPN",
        "авторизация",
        "звонок",
        "платная операция",
    ):
        assert permissioned_fragment in body


def test_examples_cover_three_domains_and_two_boundaries() -> None:
    sip = (SKILL / "examples" / "good-01-sip-timeout.md").read_text(encoding="utf-8")
    ci = (SKILL / "examples" / "good-02-ci-artifact-vs-runtime.md").read_text(encoding="utf-8")
    gui = (SKILL / "examples" / "good-03-green-ui-vs-outcome.md").read_text(encoding="utf-8")
    assertion = (SKILL / "examples" / "anti-01-exact-assertion.md").read_text(encoding="utf-8")
    compound = (SKILL / "examples" / "anti-02-compound-change.md").read_text(encoding="utf-8")

    assert "нет входящего SIP-ответа" in sip
    assert "Нельзя писать «неверный пароль»" in sip
    assert "digest" in ci and "`favors_a`" in ci and "`favors_b`" in ci
    assert "зелёный статус" in gui and "`invalid_test`" in gui
    assert "не запускает `layered-differential-diagnostics`" in assertion
    assert "одновременно меняются версия, процесс, credentials и маршрут" in compound


def test_stuck_skill_routes_first_ambiguous_failure_to_base_skill() -> None:
    body = (STUCK / "SKILL.md").read_text(encoding="utf-8")

    assert "Первый неоднозначный сбой ещё не зациклился" in body
    assert "При первом неоднозначном сбое используйте `layered-differential-diagnostics`" in body
    assert "после двух одинаковых неразличающих циклов" in body


def test_validator_accepts_complete_entry() -> None:
    validator = _load_validator()
    assert validator.validate_entries([_valid_entry()]) == []


def test_validator_rejects_missing_fields_and_unknown_verdict() -> None:
    validator = _load_validator()
    entry = _valid_entry()
    del entry["causal_contrast"]
    entry["verdict"] = "proved_root_cause"

    errors = validator.validate_entries([entry])
    assert any("causal_contrast" in error for error in errors)
    assert any("неизвестный verdict" in error for error in errors)


def test_validator_rejects_non_string_verdict_and_owner_without_crashing() -> None:
    validator = _load_validator()
    entry = _valid_entry()
    entry["verdict"] = ["inconclusive"]
    entry["owner"] = {"actor": "assistant"}

    errors = validator.validate_entries([entry])
    assert any("неизвестный verdict" in error for error in errors)
    assert any("неизвестный owner" in error for error in errors)


def test_validator_rejects_equal_hypotheses_and_predictions() -> None:
    validator = _load_validator()
    entry = _valid_entry()
    entry["hypothesis_b"] = entry["hypothesis_a"]
    entry["expected_if_b"] = entry["expected_if_a"]

    errors = validator.validate_entries([entry])
    assert any("hypothesis_a и hypothesis_b не различаются" in error for error in errors)
    assert any("expected_if_a и expected_if_b не различаются" in error for error in errors)


def test_validator_rejects_duplicate_probe_at_same_fingerprint() -> None:
    validator = _load_validator()
    first = _valid_entry()
    second = copy.deepcopy(first)
    second["verdict"] = "favors_b"

    errors = validator.validate_entries([first, second])
    assert any("дублирует probe записи 1" in error for error in errors)


def test_validator_cli_accepts_jsonl_and_rejects_bad_json(tmp_path) -> None:
    good = tmp_path / "good.jsonl"
    good.write_text(json.dumps(_valid_entry(), ensure_ascii=False) + "\n", encoding="utf-8")

    valid_result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(good)],
        capture_output=True,
        text=True,
    )
    assert valid_result.returncode == 0, valid_result.stderr
    assert "структурно корректен" in valid_result.stdout
    assert "смысловой проверки" in valid_result.stdout

    bad = tmp_path / "bad.jsonl"
    bad.write_text("{не json}\n", encoding="utf-8")

    invalid_result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(bad)],
        capture_output=True,
        text=True,
    )
    assert invalid_result.returncode == 1
    assert "некорректный JSON" in invalid_result.stderr
