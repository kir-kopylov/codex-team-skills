from __future__ import annotations

import yaml

from conftest import ROOT, load_registry


SKILL_DIR = ROOT / "plugins" / "team-skills" / "skills" / "verify"


def test_verify_separates_evidence_levels_from_tool_success() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    for level in (
        "`DISCOVERED`",
        "`PUBLIC_SOURCE`",
        "`TRANSACTION_PATH`",
        "`HUMAN_REPLY`",
        "`UNKNOWN`",
    ):
        assert level in content

    assert "Успешный вызов инструмента сам по себе K не увеличивает" in content
    assert "HTTP 200, загрузившийся интерфейс или отсутствие ошибки" in content
    assert "сами по себе не доказывают ни одного предметного поля" in content
    assert "WebFetch` с ответом 200" not in content


def test_verify_keeps_candidates_separate_from_counted_results() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    for required in (
        "Засчитанные предложения",
        "Кандидаты, не входящие в K",
        "COUNTED | CANDIDATE | REJECTED",
        "не скрывайте уже выполненную исследовательскую работу",
        "кандидаты с `unknown` сохранены отдельно",
    ):
        assert required in content


def test_verify_requires_an_executable_direct_contact_chain() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    for required in (
        "исполнитель → владелец аккаунта → канал и инструмент",
        "явное разрешение на отправку",
        "источник ответа → срок ожидания → возврат результата в карточку",
        "`CONTACT_UNAVAILABLE`",
        "не отправляйте сообщение",
        "Подготовленный черновик сообщения также не является отправкой или ответом",
    ):
        assert required in content


def test_verify_registers_the_fifteen_beds_regression() -> None:
    registry = load_registry(SKILL_DIR)
    relative_path = "examples/anti-03-unowned-seller-contact.md"
    assert relative_path in registry["example_files"]
    assert "найди 15 реальных предложений" in registry["natural_triggers"]

    good_example = (SKILL_DIR / "examples" / "good-01.md").read_text(
        encoding="utf-8"
    )
    anti_example = (SKILL_DIR / relative_path).read_text(encoding="utf-8")

    for required in (
        "15 реальных предложений box-кроватей в Алматы",
        "80×200 или 90×200",
        "ножки 10–15 см",
        "15 рабочих дней",
        "не требуется и не предлагается",
    ):
        assert required in good_example

    for required in (
        "WhatsApp",
        "Кто будет писать",
        "`CONTACT_UNAVAILABLE`",
        "не пишет продавцам",
        "не засчитывает `HUMAN_REPLY`",
    ):
        assert required in anti_example


def test_verify_keeps_the_catalog_phrase_on_all_routing_surfaces() -> None:
    phrase = "перед покупкой проверь прямо сейчас предложения по уровням доказательств и сохрани unknown"
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8").lower()
    registry = load_registry(SKILL_DIR)
    catalog = (ROOT / "catalog.md").read_text(encoding="utf-8").lower()
    openai = (SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8").lower()

    assert phrase in content
    assert phrase in registry["natural_triggers"]
    assert phrase in catalog
    assert phrase in openai


def test_verify_promotes_both_observed_failure_modes() -> None:
    data = yaml.safe_load((SKILL_DIR / "known-exceptions.yaml").read_text(encoding="utf-8"))
    exceptions = data["exceptions"]
    combined = "\n".join(
        item["symptom"] + " " + item["root_cause"] + " " + item["do_next_time"]
        for item in exceptions
    )

    assert "HTTP 200" in combined
    assert "Успех инструмента был принят за предметное доказательство" in combined
    assert "чат, WhatsApp или email" in combined
    assert "переложена на пользователя" in combined
    assert "CONTACT_UNAVAILABLE" in combined
    assert {
        "examples/good-01.md",
        "examples/anti-03-unowned-seller-contact.md",
    } <= {item["source_example"] for item in exceptions}
