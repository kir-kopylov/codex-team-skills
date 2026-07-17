from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "plugins" / "team-skills" / "skills" / "codex-quick-launch"


def test_personal_skill_uses_documented_discovery_and_invocation() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    playbook = (SKILL_DIR / "references" / "domain-playbook.md").read_text(encoding="utf-8")
    combined = skill + playbook

    for required in (
        r"%USERPROFILE%\.agents\skills\<имя>\SKILL.md",
        "$HOME/.agents/skills/<имя>/SKILL.md",
        "$имя",
        "/skills",
        "ChatGPT Desktop",
        "enabled skills появляются в slash-списке",
        "один restart",
        "фактического запуска проверены",
    ):
        assert required in combined


def test_generated_skill_name_is_normalized_before_write() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    example = (SKILL_DIR / "examples" / "good-03-legacy-prompt-migration.md").read_text(
        encoding="utf-8"
    )
    exceptions = (SKILL_DIR / "known-exceptions.yaml").read_text(encoding="utf-8")

    for required in (
        r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        "не длиннее 64 символов",
        "Кириллицу, пробелы, `_`, uppercase",
        "до записи покажите пользователю итоговый вызов `$имя`",
        "папка и `name` совпадают уже после нормализации",
        "Get-Content -Raw -Encoding UTF8",
    ):
        assert required in skill

    assert skill.index("До выбора пути") < skill.index("Создайте минимальный валидный")
    assert "`Fast_Migration`" in example
    assert "`fast-migration`" in example
    assert "`$fast-migration`" in example
    assert r"^[a-z0-9]+(?:-[a-z0-9]+)*$" in exceptions


def test_completion_is_scoped_to_the_target_surface() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    example = (SKILL_DIR / "examples" / "good-01-existing-skill.md").read_text(
        encoding="utf-8"
    )
    exceptions = (SKILL_DIR / "known-exceptions.yaml").read_text(encoding="utf-8")
    process = skill.split("## Процесс", 1)[1].split("## Границы", 1)[0]
    done = skill.split("## Definition Of Done", 1)[1].split(
        "## Опрос После Использования", 1
    )[0]

    for required in (
        "для выбранной целевой поверхности",
        "Slash-список проверяйте только для ChatGPT Desktop",
        "для CLI/IDE проверяйте `$имя` и `/skills`",
        "Статус `первое после /` применим только при явном запросе приоритета",
        "для статуса другой поверхности или незапрошенного приоритета — `не применимо`",
    ):
        assert required in process

    for required in (
        "применимые статусы обнаружения и фактического запуска",
        "для CLI/IDE отдельно проверен `/skills`",
        "Desktop-статусы помечены `не применимо`",
        "Применимый, но непроверенный статус означает честный стоп",
    ):
        assert required in done

    for required in (
        "Работаю только в CLI",
        "не требуя нерелевантного скриншота",
    ):
        assert required in example

    assert "Desktop slash-список не является условием готовности CLI/IDE" in exceptions
    assert "обнаружение, видимость в slash-списке и фактический запуск проверены" not in done


def test_failed_discovery_cannot_jump_to_plugin_or_config_guess() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    anti_example = (SKILL_DIR / "examples" / "anti-03-plugin-detour.md").read_text(
        encoding="utf-8"
    )
    combined = skill + anti_example

    for required in (
        "не создавайте marketplace/plugin для одного личного prompt",
        "не изобретайте `commands/<name>.md`",
        "Не переходите после первой неудачи к новому механизму",
        "вручную переписывать `config.toml`",
    ):
        assert required in combined

    anti_pinning = (SKILL_DIR / "examples" / "anti-01-unverified-pinning.md").read_text(
        encoding="utf-8"
    )
    assert "создаёт разумный alias" not in anti_pinning
    assert "добавлять префикс `00-`" in anti_pinning


def test_new_failure_rules_are_backed_by_shipped_examples() -> None:
    data = yaml.safe_load((SKILL_DIR / "known-exceptions.yaml").read_text(encoding="utf-8"))
    symptoms = "\n".join(item["symptom"] for item in data["exceptions"])

    assert ".codex/skills" in symptoms
    assert "commands/<имя>.md" in symptoms
    assert "installed, enabled" in symptoms
    assert "mojibake" in symptoms

    for item in data["exceptions"]:
        assert (SKILL_DIR / item["source_example"]).exists()
