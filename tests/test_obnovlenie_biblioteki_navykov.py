from __future__ import annotations

import yaml

from conftest import ROOT


SKILL_DIR = ROOT / "plugins/team-skills/skills/obnovlenie-biblioteki-navykov"


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


def test_launch_notice_cannot_replace_native_preflight() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    assert "Не завершайте первый ответ уведомлением или планом обновления" in content
    assert "До его отправки обязательно вызовите доступные read-only инструменты" in content
    assert "Первый ответ без наблюдаемого вывода этих проверок запрещён" in content
    assert "В этом же ответе верните статус" in content
    assert "не просите повторно разрешить отдельные стадии" in content


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
        "team-skills:razgrom-plana-na-naivnost",
        "списку навыков новой сессии",
    ):
        assert required in content

    assert "`INSTALLED_ON_DISK` и `LEGACY_QUARANTINED` не равны завершению" in content


def test_first_install_is_gated_by_legacy_detection_and_external_bootstrap() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    for required in (
        "START_HERE_CONNECT_CODEX_SKILLS.md",
        "START_HERE_RECONNECT_CODEX_SKILLS.md",
        "не может запустить сам себя",
        "LEGACY_TRANSITION_REQUIRED",
        "BLOCKED_LEGACY_OWNERSHIP",
        "# BEGIN codex-team-skills managed block",
        "Codex Team Skills Auto Update",
        "com.codex-team-skills.autoupdate",
        "до любой команды `marketplace add` или `plugin add`",
    ):
        assert required in content


def test_experimental_status_requires_live_end_to_end_acceptance() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    metadata = yaml.safe_load((SKILL_DIR / "skill.yaml").read_text(encoding="utf-8"))

    assert metadata["status"] == "experimental"
    assert "update → reinstall → quarantine → restart → new-session visibility" in content
    assert "CI и native smoke" in content


def test_known_exceptions_cover_delivery_duplicates_and_restart() -> None:
    data = yaml.safe_load((SKILL_DIR / "known-exceptions.yaml").read_text(encoding="utf-8"))
    exceptions = data["exceptions"]
    combined = "\n".join(
        item["symptom"] + " " + item["root_cause"] + " " + item["do_next_time"]
        for item in exceptions
    )

    assert len(exceptions) >= 7
    for required in (
        "ENOENT",
        "plugin add team-skills@codex-team-skills",
        "BLOCKED_DUPLICATE_REVIEW",
        "RESTART_PENDING",
        "BLOCKED_RESTART_UNAVAILABLE",
        "LEGACY_TRANSITION_REQUIRED",
        "START_HERE_CONNECT_CODEX_SKILLS.md",
    ):
        assert required in combined


def test_reconnect_preserves_the_package_before_native_removal() -> None:
    guide = (SKILL_DIR / "references/reconnect.md").read_text(encoding="utf-8")
    backup = guide.index("## 3. Сохранение До Любой Замены")
    remove = guide.index("codex plugin remove team-skills@codex-team-skills --json")
    assert guide.index("## 2. Проверка Владения Перед Очисткой") < backup < remove
    preservation = guide[backup:remove]
    for prerequisite in ("весь установленный пакет", "SHA-256", "свежесть", "main"):
        assert prerequisite in preservation
    assert "preserve-before-reconnect.md" in preservation


def test_source_routing_covers_installed_local_and_nested_plugin_sources() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    router = content.split("### 4.", 1)[1].split("### 5.", 1)[0]
    for distinction in (
        "Независимо от наличия установленного plugin",
        "marketplaceSource.sourceType",
        'source.source = "local"',
        "даже если plugin уже установлен",
        "Уже разрешённое переподключение",
        "Чужой или неизвестный source/ref",
    ):
        assert distinction in router
    assert router.index("до любой команды `marketplace add` или `plugin add`") < router.index("- Подтверждены Git-репозиторий")


def test_both_skills_use_one_official_cli_preflight_contract() -> None:
    relative_reference = "references/codex-cli-preflight.md"
    reference = (SKILL_DIR / relative_reference).read_text(encoding="utf-8")
    diagnostic = SKILL_DIR.parent / "sverka-aktivnoy-versii-navykov"
    for skill in (SKILL_DIR, diagnostic):
        assert relative_reference in (skill / "SKILL.md").read_text(encoding="utf-8")
    for guard in (
        "уже установленного официального приложения",
        "с тем же Codex home",
        "plugin list --json",
        "все доступные подтверждённые кандидаты",
        "Не скачивайте обходной установщик",
    ):
        assert guard in reference


def test_preservation_is_conditional_and_does_not_discard_development_work() -> None:
    content = (SKILL_DIR / "references/preserve-before-reconnect.md").read_text(
        encoding="utf-8"
    )
    for guard in (
        "Обычное\nобновление подтверждённого канонического Git marketplace",
        "из этого же SHA",
        "Номер версии не доказывает включение расширения",
        "Не меняйте эти файлы, ветку,\n   index или stash",
        "после установки нужное поведение исчезнет",
        "повторно проверьте удалённый `main`",
        "Резервную\nкопию и сведения о восстановлении не удаляйте",
    ):
        assert guard in content


def test_reconnect_instructions_ship_with_the_plugin() -> None:
    entry = (ROOT / "START_HERE_RECONNECT_CODEX_SKILLS.md").read_text(encoding="utf-8")
    bundled = "plugins/team-skills/skills/obnovlenie-biblioteki-navykov/references/reconnect.md"
    assert f"({bundled})" in entry
    assert (ROOT / bundled).is_file()
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "(references/reconnect.md)" in skill
    guide = (ROOT / bundled).read_text(encoding="utf-8")
    for reference in ("codex-cli-preflight.md", "preserve-before-reconnect.md"):
        assert f"({reference})" in guide
        assert (SKILL_DIR / "references" / reference).is_file()


def test_missing_installed_path_has_a_read_only_preservation_route() -> None:
    content = (SKILL_DIR / "references/preserve-before-reconnect.md").read_text(
        encoding="utf-8"
    )
    fallback = content.split("## Если CLI Не Раскрывает Установленный Путь", 1)[1].split(
        "## Когда Нужна Сверка Содержимого", 1
    )[0]
    for guard in (
        "installedPath = UNKNOWN_NOT_EXPOSED",
        "preservation_set",
        "Перечислите **все** версии",
        "Сохраните всё поддерево целиком",
        "Ссылки в любом компоненте пути",
        "прочитайте копии обратно",
        "**каждый пакет**",
        "Если plugin установлен, но ни точный путь, ни полный набор сохранения",
        "не доказывает путь старой установки",
    ):
        assert guard in fallback
    guide = (SKILL_DIR / "references/reconnect.md").read_text(encoding="utf-8")
    assert "полный проверенный `preservation_set`" in guide
    assert "неизвестный путь установленного пакета дают" not in guide
