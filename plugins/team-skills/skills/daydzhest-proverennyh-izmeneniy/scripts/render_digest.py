#!/usr/bin/env python3
"""Рендерит текстовый и HTML-дайджест из уже одобренных изменений без сети."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse


PRACTICE_STATUSES = {"VERIFIED", "UNVERIFIED", "MISSING"}
ANALYSIS_KINDS = {"POSITION", "INFERENCE", "HYPOTHESIS"}
AVAILABILITY_STATUSES = {"AVAILABLE", "ANNOUNCED", "DOCUMENTED", "UNKNOWN"}


class InputError(ValueError):
    """Вход не удовлетворяет контракту безопасного рендера."""


def require_text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{path}: нужна непустая строка")
    return value.strip()


def require_list(value: object, path: str) -> list[object]:
    if not isinstance(value, list):
        raise InputError(f"{path}: нужен массив")
    return value


def require_mapping(value: object, path: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise InputError(f"{path}: нужен объект")
    return value


def https_url(value: object, path: str) -> str:
    url = require_text(value, path)
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise InputError(f"{path}: разрешён только абсолютный HTTPS URL")
    return url


def optional_budget(value: object) -> dict[str, int]:
    if value is None:
        return {}
    budget = require_mapping(value, "editorial_budget")
    normalized: dict[str, int] = {}
    for key in ("max_chars", "max_words"):
        if key not in budget:
            continue
        limit = budget[key]
        if not isinstance(limit, int) or limit <= 0:
            raise InputError(f"editorial_budget.{key}: нужно положительное целое")
        normalized[key] = limit
    return normalized


def normalize(payload: object) -> dict[str, object]:
    data = require_mapping(payload, "root")
    title = require_text(data.get("title", "Дайджест проверенных изменений"), "title")
    coverage = require_mapping(data.get("coverage"), "coverage")
    coverage_status = require_text(coverage.get("status"), "coverage.status")
    if coverage_status not in {"COMPLETE", "PARTIAL"}:
        raise InputError("coverage.status: ожидается COMPLETE или PARTIAL")
    coverage_message = require_text(coverage.get("message"), "coverage.message")
    editorial_budget = optional_budget(data.get("editorial_budget"))
    items: list[dict[str, object]] = []
    for index, raw_item in enumerate(require_list(data.get("items"), "items"), start=1):
        item = require_mapping(raw_item, f"items[{index}]")
        if item.get("approval_status") != "PASS":
            raise InputError(f"items[{index}].approval_status: основная новость требует PASS")
        availability = require_text(item.get("availability"), f"items[{index}].availability")
        if availability not in AVAILABILITY_STATUSES:
            raise InputError(f"items[{index}].availability: неизвестный статус")
        sources = []
        for source_index, raw_source in enumerate(require_list(item.get("sources"), f"items[{index}].sources"), start=1):
            source = require_mapping(raw_source, f"items[{index}].sources[{source_index}]")
            sources.append({
                "label": require_text(source.get("label"), f"items[{index}].sources[{source_index}].label"),
                "url": https_url(source.get("url"), f"items[{index}].sources[{source_index}].url"),
            })
        if not sources:
            raise InputError(f"items[{index}].sources: нужна хотя бы одна ссылка")
        possibilities = []
        for possibility_index, raw_possibility in enumerate(item.get("now_possible", []), start=1):
            possibility = require_mapping(raw_possibility, f"items[{index}].now_possible[{possibility_index}]")
            practice = require_mapping(
                possibility.get("practice"), f"items[{index}].now_possible[{possibility_index}].practice"
            )
            status = require_text(practice.get("status"), f"items[{index}].now_possible[{possibility_index}].practice.status")
            if status not in PRACTICE_STATUSES:
                raise InputError(f"items[{index}].now_possible[{possibility_index}].practice.status: неизвестный статус")
            normalized_practice: dict[str, str] = {"status": status}
            if status == "MISSING":
                normalized_practice["reason"] = require_text(
                    practice.get("reason"), f"items[{index}].now_possible[{possibility_index}].practice.reason"
                )
            else:
                normalized_practice["label"] = require_text(
                    practice.get("label"), f"items[{index}].now_possible[{possibility_index}].practice.label"
                )
                normalized_practice["url"] = https_url(
                    practice.get("url"), f"items[{index}].now_possible[{possibility_index}].practice.url"
                )
                normalized_practice["success"] = require_text(
                    practice.get("success"), f"items[{index}].now_possible[{possibility_index}].practice.success"
                )
                normalized_practice["conditions"] = require_text(
                    practice.get("conditions"), f"items[{index}].now_possible[{possibility_index}].practice.conditions"
                )
                steps = require_list(
                    practice.get("steps"), f"items[{index}].now_possible[{possibility_index}].practice.steps"
                )
                if not steps or not all(isinstance(step, str) and step.strip() for step in steps):
                    raise InputError(f"items[{index}].now_possible[{possibility_index}].practice.steps: нужен непустой массив шагов")
                normalized_practice["steps"] = " → ".join(step.strip() for step in steps)
                normalized_practice["stop"] = require_text(
                    practice.get("stop"), f"items[{index}].now_possible[{possibility_index}].practice.stop"
                )
            possibilities.append({
                "text": require_text(possibility.get("text"), f"items[{index}].now_possible[{possibility_index}].text"),
                "before_limit": require_text(
                    possibility.get("before_limit"), f"items[{index}].now_possible[{possibility_index}].before_limit"
                ),
                "practice": normalized_practice,
            })
        if possibilities and availability != "AVAILABLE":
            raise InputError(
                f"items[{index}].now_possible: «Теперь можно» допустимо только при availability=AVAILABLE"
            )
        analysis = []
        for analysis_index, raw_analysis in enumerate(item.get("analysis", []), start=1):
            entry = require_mapping(raw_analysis, f"items[{index}].analysis[{analysis_index}]")
            kind = require_text(entry.get("kind"), f"items[{index}].analysis[{analysis_index}].kind")
            if kind not in ANALYSIS_KINDS:
                raise InputError(f"items[{index}].analysis[{analysis_index}].kind: неизвестная метка")
            analysis.append({"kind": kind, "text": require_text(entry.get("text"), f"items[{index}].analysis[{analysis_index}].text")})
        items.append({
            "claim_id": require_text(item.get("claim_id"), f"items[{index}].claim_id"),
            "title": require_text(item.get("title"), f"items[{index}].title"),
            "availability": availability,
            "fact": require_text(item.get("fact"), f"items[{index}].fact"),
            "before": require_text(item.get("before"), f"items[{index}].before"),
            "after": require_text(item.get("after"), f"items[{index}].after"),
            "conditions": require_text(item.get("conditions"), f"items[{index}].conditions"),
            "sources": sources,
            "now_possible": possibilities,
            "analysis": analysis,
            "decision": item.get("decision", ""),
        })
        if items[-1]["decision"]:
            items[-1]["decision"] = require_text(items[-1]["decision"], f"items[{index}].decision")
    if not items:
        raise InputError("items: нужен хотя бы один PASS-пункт")
    return {
        "title": title,
        "coverage_status": coverage_status,
        "coverage_message": coverage_message,
        "editorial_budget": editorial_budget,
        "items": items,
    }


def render_text(data: dict[str, object]) -> str:
    lines = [str(data["title"]), "", f"Покрытие: {data['coverage_status']} — {data['coverage_message']}"]
    for item in data["items"]:
        lines += ["", f"## {item['title']}", f"Суть новости: {item['fact']}", f"Раньше → сейчас: {item['before']} → {item['after']}", f"Условия: {item['conditions']}"]
        lines.append("Источники: " + " · ".join(f"{source['label']}: {source['url']}" for source in item["sources"]))
        for possibility in item["now_possible"]:
            practice = possibility["practice"]
            lines += ["", f"Теперь можно: {possibility['text']}", f"Раньше было нельзя / иначе: {possibility['before_limit']}"]
            if practice["status"] == "MISSING":
                lines.append(f"Практика: не передана — {practice['reason']}")
            else:
                marker = "проверена" if practice["status"] == "VERIFIED" else "не проверена"
                lines.append(f"Попробовать ({marker}): {practice['label']}: {practice['url']}. Условия: {practice['conditions']}. Шаги: {practice['steps']}. Успех: {practice['success']}. Стоп: {practice['stop']}")
        if item["analysis"]:
            lines.append("")
            lines.extend(f"{entry['kind']}: {entry['text']}" for entry in item["analysis"])
        if item["decision"]:
            lines += ["", f"Стоит ли вам использовать? {item['decision']}"]
    return "\n".join(lines) + "\n"


def anchor(label: str, url: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'


def render_html(data: dict[str, object]) -> str:
    body = [f"<h1>{html.escape(str(data['title']))}</h1>", f"<p><strong>Покрытие:</strong> {html.escape(str(data['coverage_status']))} — {html.escape(str(data['coverage_message']))}</p>"]
    for item in data["items"]:
        body += [f"<h2>{html.escape(item['title'])}</h2>", f"<p><strong>Суть новости:</strong> {html.escape(item['fact'])}</p>", f"<p><strong>Раньше → сейчас:</strong> {html.escape(item['before'])} → {html.escape(item['after'])}</p>", f"<p><strong>Условия:</strong> {html.escape(item['conditions'])}</p>"]
        body.append("<p><strong>Источники:</strong> " + " · ".join(anchor(source["label"], source["url"]) for source in item["sources"]) + "</p>")
        for possibility in item["now_possible"]:
            practice = possibility["practice"]
            body += [f"<p><strong>Теперь можно:</strong> {html.escape(possibility['text'])}</p>", f"<p><strong>Раньше было нельзя / иначе:</strong> {html.escape(possibility['before_limit'])}</p>"]
            if practice["status"] == "MISSING":
                body.append(f"<p><strong>Практика:</strong> не передана — {html.escape(practice['reason'])}</p>")
            else:
                marker = "проверена" if practice["status"] == "VERIFIED" else "не проверена"
                body.append(f"<p><strong>Попробовать ({marker}):</strong> {anchor(practice['label'], practice['url'])}. Условия: {html.escape(practice['conditions'])}. Шаги: {html.escape(practice['steps'])}. Успех: {html.escape(practice['success'])}. Стоп: {html.escape(practice['stop'])}</p>")
        for entry in item["analysis"]:
            body.append(f"<p><strong>{html.escape(entry['kind'])}:</strong> {html.escape(entry['text'])}</p>")
        if item["decision"]:
            body.append(f"<p><strong>Стоит ли вам использовать?</strong> {html.escape(item['decision'])}</p>")
    return "<!doctype html>\n<html lang=\"ru\"><meta charset=\"utf-8\"><body>" + "\n".join(body) + "</body></html>\n"


def atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def enforce_budget(text: str, budget: dict[str, int]) -> None:
    exceeded: list[str] = []
    if "max_chars" in budget and len(text) > budget["max_chars"]:
        exceeded.append(f"{len(text)} символов при лимите {budget['max_chars']}")
    words = re.findall(r"(?u)\b\w+\b", text)
    if "max_words" in budget and len(words) > budget["max_words"]:
        exceeded.append(f"{len(words)} слов при лимите {budget['max_words']}")
    if exceeded:
        raise InputError("editorial_budget: конфликт объёма — " + "; ".join(exceeded) + "; пункты не были отброшены")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON с уже одобренными пунктами")
    parser.add_argument("--out-dir", required=True, type=Path, help="куда записать digest.txt и digest.html")
    args = parser.parse_args(argv)
    try:
        data = normalize(json.loads(args.input.read_text(encoding="utf-8")))
        text = render_text(data)
        enforce_budget(text, data["editorial_budget"])
        args.out_dir.mkdir(parents=True, exist_ok=True)
        atomic_write(args.out_dir / "digest.txt", text)
        atomic_write(args.out_dir / "digest.html", render_html(data))
    except (OSError, json.JSONDecodeError, InputError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(f"Готово: {args.out_dir / 'digest.txt'} и {args.out_dir / 'digest.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
