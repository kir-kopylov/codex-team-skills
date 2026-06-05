from __future__ import annotations

import yaml

from conftest import ROOT, load_frontmatter, load_registry


SKILL_DIR = ROOT / "plugins" / "team-skills" / "skills" / "translate-daily-briefs"


def test_translate_daily_briefs_preserves_oksana_authorship() -> None:
    registry = load_registry(SKILL_DIR)

    assert registry["owner"] == "@kir-kopylov"
    assert "Оксана Праслова" in registry.get("authors", [])
    assert "Оксаной Прасловой" in registry["source_asset"]


def test_translate_daily_briefs_routes_translation_not_summary_or_live_state() -> None:
    frontmatter, body = load_frontmatter(SKILL_DIR / "SKILL.md")
    text = frontmatter["description"] + "\n" + body

    assert "переведи сводку на английский" in text
    assert "не сокращайте" in text
    assert "Live-state note" in text
    assert "Перевод не подтверждает" in text


def test_translate_daily_briefs_has_logging_contract_and_known_exceptions() -> None:
    body = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    known_exceptions = yaml.safe_load((SKILL_DIR / "known-exceptions.yaml").read_text(encoding="utf-8"))

    assert known_exceptions == {"exceptions": []}
    assert "## Логирование Сбоев" in body
    assert "known-exceptions.yaml" in body
    assert "exception-log.jsonl" in body
    assert "Raw logs не коммитить" in body
