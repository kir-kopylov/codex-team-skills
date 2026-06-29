#!/usr/bin/env python3
"""Пишет sanitized feedback по использованию goal-contract-shaper в локальный JSONL."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def compact(value: str) -> str:
    value = " ".join((value or "unknown").split())
    return value[:1200] if value else "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--liked", default="unknown", help="Что понравилось в использовании skill")
    parser.add_argument("--improve", default="unknown", help="Что стоит доработать")
    parser.add_argument("--outcome", default="unknown", help="Итог использования: ready, stopped, not-applicable, unknown")
    parser.add_argument("--context", default="unknown", help="Короткий обезличенный контекст без raw transcript")
    parser.add_argument("--log", default="", help="Путь к JSONL; по умолчанию ~/.codex/skill-runs/goal-contract-shaper/usage-feedback.jsonl")
    args = parser.parse_args()

    default_log = Path.home() / ".codex" / "skill-runs" / "goal-contract-shaper" / "usage-feedback.jsonl"
    log_path = Path(args.log).expanduser() if args.log else default_log
    log_path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "skill": "goal-contract-shaper",
        "liked": compact(args.liked),
        "improve": compact(args.improve),
        "outcome": compact(args.outcome),
        "context": compact(args.context),
        "source": "post-use-survey",
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"Записан feedback по skill: {log_path}")


if __name__ == "__main__":
    main()
