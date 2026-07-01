from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from conftest import ROOT


SCRIPT = ROOT / "plugins" / "team-skills" / "skills" / "goal-contract-shaper" / "scripts" / "log_usage_feedback.py"


def run_feedback_logger(tmp_path: Path, *args: str) -> dict[str, object]:
    log_path = tmp_path / "usage-feedback.jsonl"
    subprocess.run(
        [sys.executable, str(SCRIPT), "--log", str(log_path), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])


def test_feedback_logger_redacts_sensitive_fields(tmp_path: Path) -> None:
    email = "ivan.petrov" + "@" + "example.com"
    phone = "+" + "7 (999) 123-45-67"
    token = "sk-" + ("a" * 24)
    mac_path = "/Users" + "/alice/Documents/private/SKILL.md"
    windows_path = "C:" + "\\Users\\Bob\\Desktop\\note.txt"
    record = run_feedback_logger(
        tmp_path,
        "--liked",
        f"нашел проблему в {mac_path} и {windows_path}",
        "--improve",
        f"ответить на {email} или {phone}",
        "--context",
        f"url https://example.test/callback?token=secret-value&ok=1 key=plain-secret {token}",
    )

    combined = json.dumps(record, ensure_ascii=False)
    assert mac_path not in combined
    assert windows_path not in combined
    assert email not in combined
    assert phone not in combined
    assert "secret-value" not in combined
    assert "plain-secret" not in combined
    assert token not in combined
    assert "[REDACTED_PATH]" in combined
    assert "[REDACTED_EMAIL]" in combined
    assert "[REDACTED_PHONE]" in combined
    assert "[REDACTED_SECRET]" in combined
    assert record["redaction_applied"] is True
    assert set(record["redaction_types"]) == {"email", "path", "phone", "secret", "url_secret"}


def test_feedback_logger_preserves_normal_feedback(tmp_path: Path) -> None:
    record = run_feedback_logger(
        tmp_path,
        "--liked",
        "вопросы шли по одному",
        "--improve",
        "сделать блоки короче",
        "--outcome",
        "ready",
    )

    assert record["liked"] == "вопросы шли по одному"
    assert record["improve"] == "сделать блоки короче"
    assert record["outcome"] == "ready"
    assert record["context"] == "unknown"
    assert record["redaction_applied"] is False
    assert record["redaction_types"] == []
