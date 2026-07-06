#!/usr/bin/env python3
"""Пишет sanitized feedback по использованию browser-preflight в локальный JSONL."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


MAX_FIELD_LEN = 1200

REDACTION_PATTERNS = [
    (
        "private_key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
        "[REDACTED_SECRET]",
    ),
    (
        "secret",
        re.compile(r"\b(?:sk-[A-Za-z0-9_-]{20,}|gh[opsu]_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16})\b"),
        "[REDACTED_SECRET]",
    ),
    (
        "url_secret",
        re.compile(r"(?i)\b(token|api_key|key|password|secret)=([^&\s]+)"),
        lambda match: f"{match.group(1)}=[REDACTED_SECRET]",
    ),
    (
        "email",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "[REDACTED_EMAIL]",
    ),
    (
        "phone",
        re.compile(r"(?:\+7|8)[\s()-]*\d{3}[\s()-]*\d{3}[\s()-]*\d{2}[\s()-]*\d{2}"),
        "[REDACTED_PHONE]",
    ),
    (
        "path",
        re.compile(
            r"(?:/Users/[^\s'\"`)\]]+|/private/var/folders/[^\s'\"`)\]]+|"
            r"/var/folders/[^\s'\"`)\]]+|~/(?:\.codex|Downloads|Desktop|Documents|Library)[^\s'\"`)\]]*|"
            r"[A-Za-z]:\\(?:Users|Documents and Settings)\\[^\s'\"`)\]]+)"
        ),
        "[REDACTED_PATH]",
    ),
]


def normalize(value: str) -> str:
    value = " ".join((value or "unknown").split())
    return value if value else "unknown"


def sanitize(value: str) -> tuple[str, list[str]]:
    value = normalize(value)
    redaction_types: set[str] = set()

    for label, pattern, replacement in REDACTION_PATTERNS:
        def replace(match: re.Match[str]) -> str:
            redaction_types.add(label)
            return replacement(match) if callable(replacement) else replacement

        value = pattern.sub(replace, value)

    value = value[:MAX_FIELD_LEN] if value else "unknown"
    return value, sorted(redaction_types)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--liked", default="unknown", help="Что понравилось в использовании skill")
    parser.add_argument("--improve", default="unknown", help="Что стоит доработать")
    parser.add_argument("--outcome", default="unknown", help="Итог использования: ready, stopped, not-applicable, unknown")
    parser.add_argument("--context", default="unknown", help="Короткий обезличенный контекст без raw transcript")
    parser.add_argument("--log", default="", help="Путь к JSONL; по умолчанию ~/.codex/skill-runs/browser-preflight/usage-feedback.jsonl")
    args = parser.parse_args()

    default_log = Path.home() / ".codex" / "skill-runs" / "browser-preflight" / "usage-feedback.jsonl"
    log_path = Path(args.log).expanduser() if args.log else default_log
    log_path.parent.mkdir(parents=True, exist_ok=True)

    fields = {}
    redaction_types: set[str] = set()
    for field in ("liked", "improve", "outcome", "context"):
        sanitized, field_redactions = sanitize(getattr(args, field))
        fields[field] = sanitized
        redaction_types.update(field_redactions)

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "skill": "browser-preflight",
        "liked": fields["liked"],
        "improve": fields["improve"],
        "outcome": fields["outcome"],
        "context": fields["context"],
        "redaction_applied": bool(redaction_types),
        "redaction_types": sorted(redaction_types),
        "source": "post-use-survey",
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"Записан feedback по skill: {log_path}")


if __name__ == "__main__":
    main()
