from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "plugins" / "team-skills" / "skills" / "secret-file-path-only-locator"


def test_safety_contract_is_explicit() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    required = (
        "BLOCKED_UNSAFE_OUTPUT_CHANNEL",
        "PARTIAL_COVERAGE",
        "AWAITING_CLEANUP_CONFIRMATION",
        "REMEDIATION_VERIFIED",
        "synthetic",
        "revoke",
        "rotate",
        "Не добавляйте колонок `Value`, `Match`, `Line`, `Snippet`, `Hash` или `Preview`",
    )
    for phrase in required:
        assert phrase in content, f"SKILL.md не содержит safety-инвариант: {phrase}"


def test_launch_notice_cannot_replace_safe_coverage_discovery() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    assert "Не завершайте первый ответ уведомлением" in content
    assert "самостоятельно определите доступные локальные корни" in content
    assert "верните начальную coverage-матрицу" in content
    assert "не просите пользователя выполнять техническую проверку за вас" in content


def test_domain_playbook_covers_source_surfaces() -> None:
    content = (SKILL_DIR / "references" / "domain-playbook.md").read_text(encoding="utf-8")
    for phrase in ("Local files", "Git", "Mail", "Cloud docs", "Notes", "Backups and sync", "Versions and trash"):
        assert phrase in content, f"domain-playbook не покрывает поверхность: {phrase}"


def test_known_exceptions_cover_core_failure_modes() -> None:
    data = yaml.safe_load((SKILL_DIR / "known-exceptions.yaml").read_text(encoding="utf-8"))
    exceptions = data["exceptions"]
    assert len(exceptions) >= 5
    combined = "\n".join(item["symptom"] + " " + item["do_next_time"] for item in exceptions)
    for phrase in ("BLOCKED_UNSAFE_OUTPUT_CHANNEL", "PARTIAL_COVERAGE", "revoke", "PIN/CVV", "password manager"):
        assert phrase in combined
