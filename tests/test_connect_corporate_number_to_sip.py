from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

from conftest import ROOT


SKILL_DIR = (
    ROOT
    / "plugins"
    / "team-skills"
    / "skills"
    / "connect-corporate-number-to-sip"
)
SCRIPT = SKILL_DIR / "scripts" / "record_interface_exception.py"


def test_skill_contract_has_truthful_terminal_states() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    normalized = " ".join(content.split())

    for status in (
        "already_active",
        "activated",
        "request_registered",
        "blocked_human_action",
    ):
        assert status in content

    assert "request_registered" in content
    assert "не доказывает" in content
    assert "сначала повторно проверить состояние и дубли" in normalized
    assert "не менять `skill.md`" in normalized.lower()


def test_known_megafon_exceptions_are_preserved() -> None:
    data = yaml.safe_load((SKILL_DIR / "known-exceptions.yaml").read_text(encoding="utf-8"))
    exceptions = data["exceptions"]

    assert len(exceptions) == 5
    combined = "\n".join(
        " ".join(str(value) for value in item.values()) for item in exceptions
    ).lower()
    for expected in (
        "dashboard",
        "каталоге",
        "уведомления",
        "вкладкам",
        "повторный клик",
    ):
        assert expected in combined


def test_skill_contract_blocks_blind_retry() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    anti_example = (SKILL_DIR / "examples" / "anti-02.md").read_text(encoding="utf-8")
    normalized = " ".join(content.split())

    assert "Потеря страницы после клика не разрешает повторять действие" in normalized
    assert "не нажимает кнопку повторно" in anti_example


def test_interface_exception_logger_sanitizes_and_builds_proposal(tmp_path: Path) -> None:
    private_path = "/Users/example/Documents/private-note.txt"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--run-id",
            "run-001",
            "--trigger",
            "Подключить услугу на +7 900 555-01-02",
            "--intended-action",
            "Создать одну заявку",
            "--actual-action",
            "Форма открыта для user@example.test",
            "--failure-point",
            "После submit открыт request 123456789",
            "--false-assumption",
            f"Старый маршрут лежал в {private_path}",
            "--user-correction",
            "password=very-private-value",
            "--next-time-rule",
            "Сначала проверить существующий request 123456789",
            "--severity",
            "high",
            "--playbook-rule",
            "После нового redirect перечитать услуги и обращения.",
            "--regression-test",
            "Сценарий не должен повторять submit после потери подтверждения.",
            "--output-root",
            str(tmp_path / "private-run"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    log_path = tmp_path / "private-run" / "exception-log.jsonl"
    proposal_path = tmp_path / "private-run" / "patch-proposals" / "run-001.md"
    assert log_path.exists()
    assert proposal_path.exists()
    assert "Исходный skill не изменён" in result.stdout

    record = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    proposal = proposal_path.read_text(encoding="utf-8")
    serialized = json.dumps(record, ensure_ascii=False) + proposal

    for private_value in (
        "+7 900 555-01-02",
        "user@example.test",
        "123456789",
        private_path,
        "very-private-value",
    ):
        assert private_value not in serialized

    assert record["redaction_applied"] is True
    assert {"email", "phone", "private_path", "secret", "long_id"} <= set(
        record["redaction_types"]
    )
    assert "human approval" in proposal
    assert "python3 -m pytest" in proposal


def test_interface_exception_logger_refuses_git_repository(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    output_root = repo / "private-runs"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--run-id",
            "run-002",
            "--trigger",
            "Изменился интерфейс",
            "--intended-action",
            "Проверить услугу",
            "--actual-action",
            "Элемент не найден",
            "--failure-point",
            "Изменилась форма",
            "--false-assumption",
            "Старое поле осталось",
            "--next-time-rule",
            "Перечитать форму",
            "--severity",
            "medium",
            "--playbook-rule",
            "Обновить semantic anchor.",
            "--regression-test",
            "Проверить новый anchor.",
            "--output-root",
            str(output_root),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "нельзя сохранять внутри Git repository" in result.stderr
    assert not output_root.exists()
