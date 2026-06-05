from __future__ import annotations

from conftest import ROOT, load_registry


SKILL_DIR = ROOT / "plugins" / "team-skills" / "skills" / "telegram-linen-writeoff-report"


def test_telegram_linen_skill_preserves_author_and_draft_gate() -> None:
    registry = load_registry(SKILL_DIR)

    assert registry["status"] == "draft"
    assert registry["owner"] == "@kir-kopylov"
    assert "Надежда Симарзина" in registry.get("authors", [])
    assert registry.get("source_asset")
    assert registry.get("team_ready_blockers")


def test_telegram_linen_skill_requests_missing_expected_resources() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    for required in (
        "scripts/build_linen_report.py",
        "scripts/parse_telegram_export.py",
        "references/linen_rules.md",
        "references/object_aliases.md",
        "references/examples.md",
        "references/verification.md",
    ):
        assert required in text

    assert "Попросите пользователя приложить недостающие файлы" in text
    assert "Не пересоздавайте правила подсчета из памяти" in text


def test_telegram_linen_skill_has_logging_contract_and_known_exceptions() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    known_exceptions = (SKILL_DIR / "known-exceptions.yaml").read_text(encoding="utf-8")

    assert "## Логирование Сбоев" in text
    assert "known-exceptions.yaml" in text
    assert "exception-log.jsonl" in text
    assert "Raw logs не коммитить" in text
    assert "good-03-missing-package-gate.md" in known_exceptions
    assert "anti-01-no-telegram-export.md" in known_exceptions
