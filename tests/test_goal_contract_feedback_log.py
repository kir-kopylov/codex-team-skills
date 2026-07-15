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
    fine_grained_pat = "github_pat_" + ("a" * 24)
    gitlab_pat = "glpat-" + ("a" * 24)
    gitlab_pat_ending_in_hyphen = "glpat-" + ("a" * 19) + "-"
    access_token = "compound-access-value"
    refresh_token = "compound-refresh-value"
    client_secret = "compound-client-value"
    mac_path = "/Users" + "/alice/Documents/private/SKILL.md"
    linux_path = "/home" + "/alice/project/private.txt"
    windows_path = "C:" + "\\Users\\Bob\\Desktop\\note.txt"
    record = run_feedback_logger(
        tmp_path,
        "--liked",
        f"нашел проблему в {mac_path}, {linux_path} и {windows_path}",
        "--improve",
        f"ответить на {email} или {phone}",
        "--context",
        (
            "url https://example.test/callback?"
            f"token=secret-value&access_token={access_token}&refresh_token={refresh_token}&"
            f"client_secret={client_secret}&ok=1 key=plain-secret {token} {fine_grained_pat} "
            f"{gitlab_pat} {gitlab_pat_ending_in_hyphen}"
        ),
    )

    combined = json.dumps(record, ensure_ascii=False)
    assert mac_path not in combined
    assert linux_path not in combined
    assert windows_path not in combined
    assert fine_grained_pat not in combined
    assert gitlab_pat not in combined
    assert gitlab_pat_ending_in_hyphen not in combined
    assert email not in combined
    assert phone not in combined
    assert "secret-value" not in combined
    assert "plain-secret" not in combined
    assert access_token not in combined
    assert refresh_token not in combined
    assert client_secret not in combined
    assert token not in combined
    assert "access_token=[REDACTED_SECRET]" in combined
    assert "refresh_token=[REDACTED_SECRET]" in combined
    assert "client_secret=[REDACTED_SECRET]" in combined
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
        "--context",
        "monkey=banana token_type=bearer",
    )

    assert record["liked"] == "вопросы шли по одному"
    assert record["improve"] == "сделать блоки короче"
    assert record["outcome"] == "ready"
    assert record["context"] == "monkey=banana token_type=bearer"
    assert record["redaction_applied"] is False
    assert record["redaction_types"] == []
