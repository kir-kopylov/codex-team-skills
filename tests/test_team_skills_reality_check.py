from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
SKILL_DIR = ROOT / "plugins" / "team-skills" / "skills" / "team-skills-reality-check"


def test_reality_check_separates_all_five_layers_and_unknowns():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    for required in (
        "удалённый main",
        "marketplace-источник",
        "установленный plugin",
        "личные одноимённые кандидаты",
        "список навыков текущей сессии",
        "UNKNOWN_COMMAND_FAILED",
        "UNKNOWN_NOT_EXPOSED",
        "UNKNOWN_SESSION_NOT_OBSERVED",
    ):
        assert required in text


def test_reality_check_is_read_only_and_does_not_infer_session_from_disk():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    assert "Не восстанавливайте список сессии из cache" in text
    assert "POTENTIAL_PERSONAL_SHADOW" in text
    assert "OBSERVED_PERSONAL_SHADOW" in text
    assert "Не выполнять `marketplace add/upgrade/remove`" in text
    assert "Изменения среды: не выполнялись" in text


def test_reality_check_traces_visible_text_without_inventing_session_source():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    endpoint_example = (SKILL_DIR / "examples" / "good-01.md").read_text(
        encoding="utf-8"
    )

    for required in (
        "### 7. Сверить Спорный Видимый Текст",
        "один самый короткий различающий фрагмент",
        "определены оба входа: конкретный skill и различающий фрагмент",
        "отметьте сверку текста как `unknown` и пропустите её",
        "точный неизменяемый snapshot или path",
        "URL или имя ветки без наблюдаемого содержимого дают для текста `unknown`",
        "Не вычисляйте хэши",
        "не присваивайте `OBSERVED_MISMATCH` соседней границе",
        "Совпадение видимого фрагмента с файлом доказывает только совпадение текста",
        "источник остаётся `UNKNOWN_NOT_EXPOSED`",
        "это доказывает различие файлов, но не локализует границу доставки",
        "Если вопрос касается видимого текста",
        "точный недостающий вход или наблюдение отмечены как `unknown`",
    ):
        assert required in text

    assert "граница доставки не локализованы" in endpoint_example
    assert "называть remote и установленный plugin соседними слоями" in endpoint_example
    assert "remote semver против marketplace/installed semver" not in text
    assert "commit SHA только с точным commit SHA" in text
    assert "commit SHA только с source commit SHA" in text
    assert "Не сравнивайте URL или имя ветки с commit SHA" in text


def test_reality_check_first_response_is_a_snapshot_not_only_a_notice():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    launch = text.split("## Запуск Навыка", 1)[1].split("\n## ", 1)[0]

    for required in (
        "Уведомление или обещание проверки не считается рабочим шагом",
        "до отправки первого ответа выполните доступный read-only снимок",
        "repo/remote main, marketplace/plugin source, установленный plugin",
        "наблюдаемый partial/blocked результат",
        "один ближайший вопрос, какой runtime считать целевым",
        "первое действие — не текст, а вызов доступного терминала",
        "До получения фактического tool result отправлять пользователю",
        "зафиксируйте её ошибку как наблюдаемый `unknown` или `blocked`",
    ):
        assert required in launch


def test_reality_check_package_is_complete_and_experimental():
    metadata = yaml.safe_load((SKILL_DIR / "skill.yaml").read_text(encoding="utf-8"))
    exceptions = yaml.safe_load(
        (SKILL_DIR / "known-exceptions.yaml").read_text(encoding="utf-8")
    )

    assert metadata["status"] == "experimental"
    assert len(metadata["example_files"]) == 5
    assert len(exceptions["exceptions"]) >= 5
    for relative_path in metadata["example_files"]:
        assert (SKILL_DIR / relative_path).is_file()
    assert (SKILL_DIR / "references" / "domain-playbook.md").is_file()
