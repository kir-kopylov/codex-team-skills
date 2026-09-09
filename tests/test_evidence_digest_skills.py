"""Регрессии для трёх навыков доказательного журнала.

Проверки не доказывают истинность внешних источников. Они защищают именно
локальные границы: недопущенный тезис не рендерится, практический путь не
подменяется общей ссылкой, а совпадение времени не становится квитанцией.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from conftest import ROOT


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RENDER = load_module(
    "render_digest",
    ROOT / "plugins/team-skills/skills/daydzhest-proverennyh-izmeneniy/scripts/render_digest.py",
)
RECEIPT = load_module(
    "verify_receipt",
    ROOT / "plugins/team-skills/skills/podtverzhdenie-planovoy-rassylki/scripts/verify_receipt.py",
)


def approved_digest() -> dict:
    return {
        "title": "Тестовый журнал",
        "coverage": {"status": "COMPLETE", "message": "Все обязательные источники проверены."},
        "items": [
            {
                "claim_id": "csv-export",
                "approval_status": "PASS",
                "availability": "AVAILABLE",
                "title": "Экспорт CSV",
                "fact": "Экспорт CSV доступен на плане Pro.",
                "before": "На плане Pro экспорт не поддерживался.",
                "after": "На плане Pro доступен экспорт CSV.",
                "conditions": "Только роль администратора.",
                "sources": [{"label": "Документация", "url": "https://example.test/csv"}],
                "now_possible": [
                    {
                        "text": "Скачать отчёт в CSV.",
                        "before_limit": "Раньше CSV для этого плана не поддерживался.",
                        "practice": {
                            "status": "UNVERIFIED",
                            "label": "Открыть инструкцию",
                            "url": "https://example.test/how-to",
                            "conditions": "Только тестовый отчёт администратора.",
                            "steps": ["Открыть тестовый отчёт", "Выбрать CSV"],
                            "success": "Файл CSV появился в загрузках.",
                            "stop": "Остановиться, если форма просит изменить настройки аккаунта.",
                        },
                    }
                ],
                "analysis": [{"kind": "INFERENCE", "text": "Это может сократить ручное копирование."}],
                "decision": "Проверьте на одной безопасной выгрузке.",
            }
        ],
    }


def receipt_packet() -> dict:
    scope = {
        "mailbox": "reader@example.test",
        "start": "2026-09-10T08:20:00+06:00",
        "end": "2026-09-10T08:40:00+06:00",
        "query": "subject:Тестовый-журнал",
        "copy_rule": "Совпадают delivery_key и получатель.",
    }
    expected = {
        "run_id": "2026-09-10",
        "artifact_sha256": "a" * 64,
        "recipients": ["reader@example.test"],
        "cc": [],
        "bcc": [],
        "attachments": [],
        "subject": "Тестовый журнал",
        "text_body": "Проверенный текст\n",
        "html_body": "<p>Проверенный текст</p>\n",
        "deadline": "2026-09-10T08:30:00+06:00",
        "duplicate_scope": scope,
    }
    message = {
        "turn_id": "turn-42",
        "message_id": "provider-123",
        "artifact_sha256": "a" * 64,
        "recipients": ["reader@example.test"],
        "cc": [],
        "bcc": [],
        "attachments": [],
        "subject": "Тестовый журнал",
        "text_body": "Проверенный текст\r\n",
        "html_body": "<p>Проверенный текст</p>\r\n",
        "sent_at": "2026-09-10T08:28:00+06:00",
        "provider_response": {"message_id": "provider-123", "accepted_at": "2026-09-10T08:28:10+06:00"},
    }
    received = {**message, "received_at": "2026-09-10T08:29:00+06:00"}
    return {
        "expected": expected,
        "scheduler": {"run_id": "2026-09-10", "turn_id": "turn-42", "started_at": "2026-09-10T08:27:00+06:00"},
        "send": message,
        "received": [received],
        "duplicate_search": {"complete": True, "scope": scope, "message_ids": ["provider-123"]},
        "replay_history": {"complete": True, "previous_run_ids": []},
    }


def test_renderer_keeps_fact_source_practice_and_analysis_separate(tmp_path: Path) -> None:
    data = RENDER.normalize(approved_digest())
    text = RENDER.render_text(data)
    rendered_html = RENDER.render_html(data)

    for fragment in ("Экспорт CSV доступен на плане Pro.", "https://example.test/csv", "INFERENCE"):
        assert fragment in text
        assert fragment in rendered_html

    RENDER.atomic_write(tmp_path / "digest.txt", text)
    RENDER.atomic_write(tmp_path / "digest.html", rendered_html)
    assert (tmp_path / "digest.txt").exists()
    assert (tmp_path / "digest.html").exists()


def test_renderer_blocks_non_pass_claim() -> None:
    data = approved_digest()
    data["items"][0]["approval_status"] = "UNKNOWN"
    with pytest.raises(RENDER.InputError, match="PASS"):
        RENDER.normalize(data)


def test_renderer_requires_practice_per_now_possible() -> None:
    data = approved_digest()
    del data["items"][0]["now_possible"][0]["practice"]
    with pytest.raises(RENDER.InputError, match="practice"):
        RENDER.normalize(data)


def test_renderer_blocks_now_possible_before_availability() -> None:
    data = approved_digest()
    data["items"][0]["availability"] = "ANNOUNCED"
    with pytest.raises(RENDER.InputError, match="availability=AVAILABLE"):
        RENDER.normalize(data)


def test_renderer_reports_budget_conflict_without_dropping_items() -> None:
    data = RENDER.normalize(approved_digest())
    text = RENDER.render_text(data)
    with pytest.raises(RENDER.InputError, match="конфликт объёма"):
        RENDER.enforce_budget(text, {"max_chars": 20})
    assert "Экспорт CSV доступен на плане Pro." in text


def test_receipt_requires_direct_chain_and_all_expected_content() -> None:
    result = RECEIPT.assess(receipt_packet())
    assert result["status"] == "PASS"
    assert result["failures"] == []

    wrong_html = receipt_packet()
    wrong_html["received"][0]["html_body"] = "<p>Другой выпуск</p>\n"
    result = RECEIPT.assess(wrong_html)
    assert result["status"] == "FAIL"
    assert "HTML" in " ".join(result["failures"])


def test_receipt_does_not_treat_timing_as_origin_proof() -> None:
    data = receipt_packet()
    data["send"]["turn_id"] = "manual-turn"
    result = RECEIPT.assess(data)
    assert result["status"] == "FAIL"
    assert "turn_id" in " ".join(result["failures"])

    absent_scheduler = receipt_packet()
    absent_scheduler["scheduler"] = None
    result = RECEIPT.assess(absent_scheduler)
    assert result["status"] == "UNPROVEN"
    assert result["prior_receipt_preserved"] is False


def test_receipt_requires_provider_chain_scope_and_replay_guard() -> None:
    outside_scope = receipt_packet()
    outside_scope["received"][0]["received_at"] = "2026-09-10T01:00:00+06:00"
    result = RECEIPT.assess(outside_scope)
    assert result["status"] == "FAIL"
    assert "интервала" in " ".join(result["failures"])

    replayed = receipt_packet()
    replayed["replay_history"]["previous_run_ids"] = ["2026-09-10"]
    result = RECEIPT.assess(replayed)
    assert result["status"] == "FAIL"
    assert "уже был использован" in " ".join(result["failures"])

    hidden_bcc = receipt_packet()
    hidden_bcc["send"]["bcc"] = ["hidden@example.test"]
    result = RECEIPT.assess(hidden_bcc)
    assert result["status"] == "FAIL"
    assert "bcc" in " ".join(result["failures"])

    no_provider_response = receipt_packet()
    del no_provider_response["send"]["provider_response"]
    result = RECEIPT.assess(no_provider_response)
    assert result["status"] == "UNPROVEN"
    assert "provider_response" in " ".join(result["unproven"])
