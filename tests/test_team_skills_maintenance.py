from __future__ import annotations

import yaml

from conftest import ROOT


SKILL_DIR = ROOT / "plugins/team-skills/skills/team-skills-maintenance"


def test_maintenance_uses_only_native_codex_delivery() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    for required in (
        "codex --version",
        "codex plugin --help",
        "codex plugin list --json",
        "codex plugin marketplace upgrade codex-team-skills --json",
        "codex plugin marketplace add kir-kopylov/codex-team-skills --ref main --json",
        "codex plugin add team-skills@codex-team-skills --json",
        "BLOCKED_CODEX_CLI",
    ):
        assert required in content

    assert "фоновый обновлятор" in content
    assert "прямую правку кэша" in content


def test_exact_catalog_phrase_authorizes_the_whole_cycle() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    catalog = (ROOT / "catalog.md").read_text(encoding="utf-8")

    assert "Обнови библиотеку навыков." in catalog
    assert "разрешает один полный цикл" in content
    assert "Не дробите это разрешение на отдельные вопросы" in content
    for stage in (
        "штатное обновление",
        "повторную установку пакета",
        "перенос доказанных дублей в карантин",
        "безопасного перезапуска Codex",
        "проверку после него",
    ):
        assert stage in content


def test_duplicate_migration_is_exact_recoverable_and_scoped() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    for required in (
        "frontmatter `name` точно совпадает с именем каталога",
        "такое же имя есть в проверенном каноническом списке",
        "атомарным переименованием без перезаписи",
        "деревом файлов и SHA-256",
        "Не удаляйте карантин в этом запуске",
        "Все уникальные личные навыки должны остаться байт-в-байт без изменений",
        "Не трогайте repo-scoped `.agents/skills`",
        "BLOCKED_DUPLICATE_REVIEW",
    ):
        assert required in content


def test_runtime_success_requires_a_new_session() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    for required in (
        "INSTALLED_ON_DISK",
        "LEGACY_QUARANTINED",
        "RESTART_PENDING",
        "BLOCKED_RESTART_UNAVAILABLE",
        "LIVE_VERIFIED",
        "team-skills:production-forensic-auditor",
        "списку навыков новой сессии",
    ):
        assert required in content

    assert "`INSTALLED_ON_DISK` и `LEGACY_QUARANTINED` не равны завершению" in content


def test_known_exceptions_cover_delivery_duplicates_and_restart() -> None:
    data = yaml.safe_load((SKILL_DIR / "known-exceptions.yaml").read_text(encoding="utf-8"))
    exceptions = data["exceptions"]
    combined = "\n".join(
        item["symptom"] + " " + item["root_cause"] + " " + item["do_next_time"]
        for item in exceptions
    )

    assert len(exceptions) >= 5
    for required in (
        "ENOENT",
        "plugin add team-skills@codex-team-skills",
        "BLOCKED_DUPLICATE_REVIEW",
        "RESTART_PENDING",
        "BLOCKED_RESTART_UNAVAILABLE",
    ):
        assert required in combined
