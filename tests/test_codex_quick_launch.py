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
        "фактического запуска и эквивалентности исходному prompt проверены",
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
    catalog = (ROOT / "catalog.md").read_text(encoding="utf-8")
    example = (SKILL_DIR / "examples" / "good-01-existing-skill.md").read_text(
        encoding="utf-8"
    )
    priority_example = (SKILL_DIR / "examples" / "good-02-menu-priority.md").read_text(
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
        "применимые статусы обнаружения, фактического запуска и эквивалентности",
        "skill правильного scope",
        "отсутствие несогласованной коллизии имени",
        "UTF-8 без BOM",
        "успешный результат штатного валидатора",
        "для CLI/IDE отдельно проверен `/skills`",
        "Desktop-статусы помечены `не применимо`",
        "Применимый непроверенный статус или проверенный результат `нет` означает честный стоп",
    ):
        assert required in done

    for required in (
        "Работаю только в CLI",
        "не требуя нерелевантного скриншота",
    ):
        assert required in example

    assert "Desktop slash-список не является условием готовности CLI/IDE" in exceptions
    assert "для ChatGPT Desktop проверить его в slash-списке" in catalog
    assert "для CLI/IDE — через `/skills`" in catalog
    assert "на выбранной поверхности проверить `$имя`" in catalog
    assert "увидеть его в slash-списке Desktop и проверить `$имя`" not in catalog
    assert "если её нельзя определить из входа или среды, задаёт один вопрос" in priority_example
    assert "обнаружение, видимость в slash-списке и фактический запуск проверены" not in done


def test_target_surface_is_fixed_before_mutation() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    process = skill.split("## Процесс", 1)[1].split("## Границы", 1)[0]

    for required in (
        "До выбора проверок зафиксируйте целевую поверхность",
        "Явно названная целевая поверхность имеет приоритет",
        "Где нужен быстрый вызов: ChatGPT Desktop, CLI или IDE?",
        "Не создавайте файл и не выполняйте restart до ответа",
    ):
        assert required in process

    assert process.index("До выбора проверок") < process.index("До любой записи")


def test_prewrite_name_collision_cannot_overwrite_another_skill() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    example = (SKILL_DIR / "examples" / "good-03-legacy-prompt-migration.md").read_text(
        encoding="utf-8"
    )
    exceptions = (SKILL_DIR / "known-exceptions.yaml").read_text(encoding="utf-8")

    for required in (
        "До любой записи проверьте целевой path",
        "все обнаруживаемые skills с таким же `name`",
        "не перезаписывайте файл",
        "Skill неверного scope с тем же именем считайте коллизией",
        "вернитесь к шагу 7",
        "снова покажите новый `$имя`",
        "повторите collision-check",
        "Не пишите файл, пока цикл не прошёл без коллизии",
    ):
        assert required in skill

    assert skill.index("До любой записи") < skill.index("Создайте минимальный валидный")
    assert "Занятый другим поведением файл не перезаписывает" in example
    assert "снова показывает новый `$вызов` и повторяет collision-check" in example
    assert "коллизию целевого path и поля `name` до изменяющего действия" in exceptions


def test_reuse_matches_scope_and_runtime_availability() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    example = (SKILL_DIR / "examples" / "good-01-existing-skill.md").read_text(
        encoding="utf-8"
    )
    exceptions = (SKILL_DIR / "known-exceptions.yaml").read_text(encoding="utf-8")
    process = skill.split("## Процесс", 1)[1].split("## Границы", 1)[0]

    for required in (
        "Зафиксируйте целевой scope",
        "path, `name`, scope, enabled-state",
        "Переиспользуйте только skill нужного scope",
        "Skill неверного scope не считайте reuse",
        "создавайте отдельный skill правильного scope",
        "Если skill правильного scope disabled, не создавайте дубль",
        "disabled: да",
        "цель достигнута: нет",
        "отдельной явно авторизованной задачей на включение вне этого skill",
        "discovery равен `false` или `unknown`",
        "тоже не создавайте дубль или alias",
        "read-only проверки шага 14 и не более одного restart",
        "обнаружение: не подтверждено",
    ):
        assert required in process

    assert "enabled skill нужного scope" in example
    assert "repo-scoped вариант при явной цели переносит" in example
    assert "enabled с discovery `false/unknown` проверяет без записи" in example
    assert "состояние на диске: переиспользован" in example
    assert "repo-scoped, disabled или не обнаруживается" in exceptions
    assert "enabled с discovery `false/unknown`" in exceptions
    assert "отдельным handoff на задачу включения" in exceptions
    assert "запросите отдельное согласие на включение" not in process
    assert process.index("Зафиксируйте целевой scope") < process.index("До любой записи")


def test_successful_invocation_does_not_prove_behavior_equivalence() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    catalog = (ROOT / "catalog.md").read_text(encoding="utf-8")
    metadata = (SKILL_DIR / "skill.yaml").read_text(encoding="utf-8")
    example = (SKILL_DIR / "examples" / "good-01-existing-skill.md").read_text(
        encoding="utf-8"
    )
    process = skill.split("## Процесс", 1)[1].split("## Границы", 1)[0]
    done = skill.split("## Definition Of Done", 1)[1].split(
        "## Опрос После Использования", 1
    )[0]

    for required in (
        "1–3 наблюдаемых инварианта",
        "безопасную недеструктивную репрезентативную пробу",
        "Сам факт запуска не доказывает эквивалентность поведения",
        "поведение сохранено: не подтверждено",
        "Статус поведения применим всегда",
        "состояние на диске: переиспользован / создан / обновлён",
        "Успешный reuse получает `переиспользован`",
        "для проверенного отрицательного результата — `нет`",
    ):
        assert required in process

    assert "эквивалентности исходному prompt" in done
    assert "сохранение исходного поведения" in catalog
    assert "сохранение исходного поведения" in metadata
    assert "сохранение поведения на этой пробе" in example
    assert "доказанное несовпадение — как `нет`" in (SKILL_DIR / "known-exceptions.yaml").read_text(
        encoding="utf-8"
    )


def test_windows_validation_uses_utf8_without_bom() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    example = (SKILL_DIR / "examples" / "good-03-legacy-prompt-migration.md").read_text(
        encoding="utf-8"
    )
    exceptions = (SKILL_DIR / "known-exceptions.yaml").read_text(encoding="utf-8")
    playbook = (SKILL_DIR / "references" / "domain-playbook.md").read_text(
        encoding="utf-8"
    )
    for required in (
        "UTF-8 без BOM",
        "UTF8Encoding(false)",
        "python -X utf8",
        "UnicodeDecodeError",
        "No YAML frontmatter",
    ):
        assert required in skill

    assert "`UnicodeDecodeError` при запуске без `-X utf8` не означает" in skill
    assert "`Out-File` или `Set-Content -Encoding UTF8`" in skill
    assert "пишет UTF-8 без BOM и запускает validator через `python -X utf8`" in example
    assert "первые байты на BOM" in exceptions
    assert "видимая строка `---` при `No YAML frontmatter`" in playbook


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


def test_recovery_path_is_conditional_on_observed_os() -> None:
    anti_example = (SKILL_DIR / "examples" / "anti-03-plugin-detour.md").read_text(
        encoding="utf-8"
    )

    assert "После определения ОС" in anti_example
    assert r"%USERPROFILE%\.agents\skills\zachem\SKILL.md" in anti_example
    assert "$HOME/.agents/skills/zachem/SKILL.md" in anti_example


def test_new_failure_rules_are_backed_by_shipped_examples() -> None:
    data = yaml.safe_load((SKILL_DIR / "known-exceptions.yaml").read_text(encoding="utf-8"))
    symptoms = "\n".join(item["symptom"] for item in data["exceptions"])

    assert ".codex/skills" in symptoms
    assert "commands/<имя>.md" in symptoms
    assert "installed, enabled" in symptoms
    assert "mojibake" in symptoms
    assert "UnicodeDecodeError" in symptoms
    assert "тот же path" in symptoms

    for item in data["exceptions"]:
        assert (SKILL_DIR / item["source_example"]).exists()
