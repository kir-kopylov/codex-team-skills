#!/usr/bin/env python3
"""Проверяет локальный пакет доказательств одной плановой почтовой доставки.

Модуль не читает Gmail и ничего не отправляет. Его PASS ограничен переданным
пакетом: запуск, отправка, ответ провайдера, полученная копия, область поиска
дублей и история использованных run_id.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class InputError(ValueError):
    """Пакет не содержит минимального ожидаемого выпуска."""


def mapping(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InputError(f"{path}: нужен объект")
    return value


def text(value: object, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise InputError(f"{path}: нужна {'строка' if allow_empty else 'непустая строка'}")
    return value


def strings(value: object, path: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise InputError(f"{path}: нужен массив непустых строк")
    if nonempty and not value:
        raise InputError(f"{path}: нужен непустой массив")
    return value


def sha256(value: object, path: str) -> str:
    digest = text(value, path)
    if not SHA256_RE.fullmatch(digest):
        raise InputError(f"{path}: нужен SHA-256 в нижнем hex")
    return digest


def normalized_body(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def parse_time(value: object, path: str) -> datetime:
    raw = text(value, path)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise InputError(f"{path}: нужен ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise InputError(f"{path}: нужна временная зона")
    return parsed


def optional_mapping(value: object, path: str, unproven: list[str]) -> dict[str, Any] | None:
    if value is None:
        unproven.append(f"нет {path}")
        return None
    if not isinstance(value, dict):
        unproven.append(f"{path} имеет неверный формат")
        return None
    return value


def same_recipients(left: list[str], right: list[str]) -> bool:
    return sorted(address.casefold() for address in left) == sorted(address.casefold() for address in right)


def compare_message(expected: dict[str, Any], actual: dict[str, Any], prefix: str, failures: list[str], unproven: list[str]) -> bool:
    """Сравнить фиксированное тело; вернуть, наблюдалась ли правильная копия."""
    observed = False
    try:
        recipients = strings(actual.get("recipients"), f"{prefix}.recipients", nonempty=True)
        if not same_recipients(expected["recipients"], recipients):
            failures.append(f"{prefix}: получатели не совпали")
        if text(actual.get("subject"), f"{prefix}.subject") != expected["subject"]:
            failures.append(f"{prefix}: тема не совпала")
        if normalized_body(text(actual.get("text_body"), f"{prefix}.text_body", allow_empty=True)) != expected["text_body"]:
            failures.append(f"{prefix}: текст не совпал")
        if expected["html_body"] is not None:
            if normalized_body(text(actual.get("html_body"), f"{prefix}.html_body", allow_empty=True)) != expected["html_body"]:
                failures.append(f"{prefix}: HTML не совпал")
        if prefix == "send":
            if sha256(actual.get("artifact_sha256"), "send.artifact_sha256") != expected["artifact_sha256"]:
                failures.append("send: отпечаток исходящего выпуска не совпал")
            for key in ("cc", "bcc", "attachments"):
                extras = strings(actual.get(key), f"send.{key}")
                if extras:
                    failures.append(f"send: V1 не допускает непустой {key}")
        observed = not failures
    except InputError as error:
        unproven.append(str(error))
    return observed


def normalize_expected(payload: dict[str, Any]) -> dict[str, Any]:
    raw = mapping(payload.get("expected"), "expected")
    scope = mapping(raw.get("duplicate_scope"), "expected.duplicate_scope")
    html_body = raw.get("html_body")
    if html_body is not None:
        html_body = normalized_body(text(html_body, "expected.html_body", allow_empty=True))
    extra = {key: strings(raw.get(key, []), f"expected.{key}") for key in ("cc", "bcc", "attachments")}
    return {
        "run_id": text(raw.get("run_id"), "expected.run_id"),
        "artifact_sha256": sha256(raw.get("artifact_sha256"), "expected.artifact_sha256"),
        "recipients": strings(raw.get("recipients"), "expected.recipients", nonempty=True),
        "subject": text(raw.get("subject"), "expected.subject"),
        "text_body": normalized_body(text(raw.get("text_body"), "expected.text_body", allow_empty=True)),
        "html_body": html_body,
        "deadline": parse_time(raw.get("deadline"), "expected.deadline"),
        "duplicate_scope": {
            key: text(scope.get(key), f"expected.duplicate_scope.{key}")
            for key in ("mailbox", "start", "end", "query", "copy_rule")
        },
        "scope_start": parse_time(scope.get("start"), "expected.duplicate_scope.start"),
        "scope_end": parse_time(scope.get("end"), "expected.duplicate_scope.end"),
        "extras": extra,
    }


def assess_prior_receipt(raw: object, expected: dict[str, Any], unproven: list[str]) -> bool:
    if raw is None:
        return False
    if not isinstance(raw, dict):
        unproven.append("prior_receipt имеет неверный формат")
        return False
    try:
        if text(raw.get("run_id"), "prior_receipt.run_id") != expected["run_id"]:
            unproven.append("prior_receipt относится к другому run_id")
            return False
        sha256(raw.get("artifact_sha256"), "prior_receipt.artifact_sha256")
        text(raw.get("message_id"), "prior_receipt.message_id")
        parse_time(raw.get("recorded_at"), "prior_receipt.recorded_at")
    except InputError as error:
        unproven.append(str(error))
        return False
    return True


def assess(payload: object) -> dict[str, Any]:
    root = mapping(payload, "root")
    expected = normalize_expected(root)
    failures: list[str] = []
    unproven: list[str] = []
    if expected["scope_start"] > expected["scope_end"]:
        raise InputError("expected.duplicate_scope: начало позже конца")
    if any(expected["extras"].values()):
        unproven.append("V1 проверяет только письма без CC, BCC и вложений")
    prior_receipt_preserved = assess_prior_receipt(root.get("prior_receipt"), expected, unproven)

    scheduler = optional_mapping(root.get("scheduler"), "scheduler", unproven)
    send = optional_mapping(root.get("send"), "send", unproven)
    message_id: str | None = None
    scheduler_started_at: datetime | None = None
    send_accepted_at: datetime | None = None
    turn_id: str | None = None

    if scheduler is not None:
        try:
            if text(scheduler.get("run_id"), "scheduler.run_id") != expected["run_id"]:
                failures.append("scheduler: run_id не совпал с ожидаемым выпуском")
            turn_id = text(scheduler.get("turn_id"), "scheduler.turn_id")
            scheduler_started_at = parse_time(scheduler.get("started_at"), "scheduler.started_at")
        except InputError as error:
            unproven.append(str(error))

    if send is not None:
        try:
            send_turn_id = text(send.get("turn_id"), "send.turn_id")
            message_id = text(send.get("message_id"), "send.message_id")
            sent_at = parse_time(send.get("sent_at"), "send.sent_at")
            provider = mapping(send.get("provider_response"), "send.provider_response")
            if text(provider.get("message_id"), "send.provider_response.message_id") != message_id:
                failures.append("send: message_id не подтверждён ответом провайдера")
            send_accepted_at = parse_time(provider.get("accepted_at"), "send.provider_response.accepted_at")
            if scheduler_started_at is not None and sent_at < scheduler_started_at:
                failures.append("send: отправка произошла раньше запуска планировщика")
            if send_accepted_at < sent_at:
                failures.append("send: ответ провайдера раньше вызова отправки")
            if turn_id is None:
                unproven.append("невозможно связать отправку с планировщиком")
            elif send_turn_id != turn_id:
                failures.append("send: turn_id не совпал с планировщиком")
            compare_message(expected, send, "send", failures, unproven)
        except InputError as error:
            unproven.append(str(error))
            message_id = None

    raw_received = root.get("received", [])
    if not isinstance(raw_received, list):
        unproven.append("received имеет неверный формат")
        raw_received = []
    matched: list[dict[str, Any]] = []
    delivery_observed = False
    if message_id:
        for entry in raw_received:
            if isinstance(entry, dict) and entry.get("message_id") == message_id:
                matched.append(entry)
        if not matched:
            unproven.append("не найдена полученная копия с message_id отправки")
        elif len(matched) > 1:
            failures.append("для одного message_id передано несколько полученных копий")
        else:
            received = matched[0]
            failures_before = len(failures)
            compare_message(expected, received, "received", failures, unproven)
            try:
                received_at = parse_time(received.get("received_at"), "received.received_at")
                if send_accepted_at is not None and received_at < send_accepted_at:
                    failures.append("received: письмо получено раньше ответа провайдера")
                if received_at > expected["deadline"]:
                    failures.append("received: письмо получено позже дедлайна")
                if not (expected["scope_start"] <= received_at <= expected["scope_end"]):
                    failures.append("received: письмо вне объявленного интервала поиска")
            except InputError as error:
                unproven.append(str(error))
            delivery_observed = len(failures) == failures_before
    else:
        unproven.append("нет message_id для связи с полученной копией")

    search = optional_mapping(root.get("duplicate_search"), "duplicate_search", unproven)
    checked_scope: dict[str, str] | None = None
    if search is not None:
        scope = optional_mapping(search.get("scope"), "duplicate_search.scope", unproven)
        if scope is not None:
            try:
                checked_scope = {key: text(scope.get(key), f"duplicate_search.scope.{key}") for key in expected["duplicate_scope"]}
                if checked_scope != expected["duplicate_scope"]:
                    unproven.append("duplicate_search: область поиска не совпала с объявленной")
            except InputError as error:
                unproven.append(str(error))
                checked_scope = None
        if search.get("complete") is not True:
            unproven.append("duplicate_search: поиск неполный")
        ids = search.get("message_ids")
        if not isinstance(ids, list) or not all(isinstance(item, str) and item for item in ids):
            unproven.append("duplicate_search.message_ids имеет неверный формат")
        elif search.get("complete") is True and checked_scope == expected["duplicate_scope"] and message_id:
            if len(ids) == 1 and ids[0] == message_id:
                pass
            elif len(ids) > 1:
                failures.append("duplicate_search: найдено больше одной копии выпуска")
            else:
                unproven.append("duplicate_search: результат не согласуется с message_id отправки")

    replay = optional_mapping(root.get("replay_history"), "replay_history", unproven)
    if replay is not None:
        if replay.get("complete") is not True:
            unproven.append("replay_history: история run_id неполная")
        previous_run_ids = replay.get("previous_run_ids")
        if not isinstance(previous_run_ids, list) or not all(isinstance(item, str) and item for item in previous_run_ids):
            unproven.append("replay_history.previous_run_ids имеет неверный формат")
        elif expected["run_id"] in previous_run_ids:
            failures.append("replay_history: run_id уже был использован")

    if failures:
        status = "FAIL"
    elif unproven:
        status = "UNPROVEN"
    else:
        status = "PASS"
    return {
        "status": status,
        "scheduled_delivery_status": status,
        "delivery_observed": delivery_observed,
        "run_id": expected["run_id"],
        "artifact_sha256": expected["artifact_sha256"],
        "message_id": message_id,
        "failures": failures,
        "unproven": unproven,
        "checked_duplicate_scope": checked_scope,
        "prior_receipt_preserved": prior_receipt_preserved,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON-пакет доказательств одного выпуска")
    args = parser.parse_args(argv)
    try:
        result = assess(json.loads(args.input.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, InputError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
