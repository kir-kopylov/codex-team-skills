#!/usr/bin/env python3
"""Санирует карточку интерфейсного сбоя и готовит patch proposal вне repo."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


SKILL_NAME = "connect-corporate-number-to-sip"
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?:\+?\d[\s().-]*){10,15}")
PRIVATE_PATH_RE = re.compile(
    r"(?:/Users/[^/\s]+/(?:Downloads|Library|Desktop|Documents)/[^\s`)\]]+"
    r"|~/(?:Downloads|Desktop|Documents)/[^\s`)\]]+)"
)
SECRET_RE = re.compile(
    r"(?i)\b(?:password|пароль|token|secret|sip[-_ ]?password)\b"
    r"\s*[:=]\s*[^\s,;]+"
)
LONG_ID_RE = re.compile(r"(?<![\w<>])\d{6,}(?![\w<>])")


def sanitize(value: str) -> tuple[str, list[str]]:
    """Вернуть очищенный текст и список применённых типов редактирования."""

    result = value
    redactions: list[str] = []
    for label, pattern, replacement in (
        ("secret", SECRET_RE, "<secret>"),
        ("email", EMAIL_RE, "<email>"),
        ("phone", PHONE_RE, "<phone>"),
        ("private_path", PRIVATE_PATH_RE, "<private-path>"),
        ("long_id", LONG_ID_RE, "<id>"),
    ):
        result, count = pattern.subn(replacement, result)
        if count:
            redactions.append(label)
    return result, redactions


def safe_run_id(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-._")
    if not normalized:
        raise SystemExit("run_id после нормализации пуст")
    return normalized[:80]


def refuse_repository_path(path: Path) -> None:
    """Не позволять сохранять приватные карточки внутри Git repository."""

    resolved = path.expanduser().resolve()
    for candidate in (resolved, *resolved.parents):
        if (candidate / ".git").exists():
            raise SystemExit("Отказ: приватный журнал нельзя сохранять внутри Git repository")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--trigger", required=True)
    parser.add_argument("--intended-action", required=True)
    parser.add_argument("--actual-action", required=True)
    parser.add_argument("--failure-point", required=True)
    parser.add_argument("--false-assumption", required=True)
    parser.add_argument("--user-correction", default="unknown")
    parser.add_argument("--next-time-rule", required=True)
    parser.add_argument("--severity", choices=("low", "medium", "high"), required=True)
    parser.add_argument("--playbook-rule", required=True)
    parser.add_argument("--regression-test", required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path.home() / ".codex" / "skill-runs" / SKILL_NAME,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_root = args.output_root.expanduser()
    refuse_repository_path(output_root)

    raw_fields = {
        "trigger": args.trigger,
        "intended_action": args.intended_action,
        "actual_action": args.actual_action,
        "failure_point": args.failure_point,
        "false_assumption": args.false_assumption,
        "user_correction": args.user_correction,
        "next_time_rule": args.next_time_rule,
        "playbook_rule": args.playbook_rule,
        "regression_test": args.regression_test,
    }
    clean_fields: dict[str, str] = {}
    redaction_types: set[str] = set()
    for key, value in raw_fields.items():
        clean, applied = sanitize(value)
        clean_fields[key] = clean
        redaction_types.update(applied)

    run_id = safe_run_id(args.run_id)
    output_root.mkdir(parents=True, exist_ok=True)
    proposal_dir = output_root / "patch-proposals"
    proposal_dir.mkdir(parents=True, exist_ok=True)

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "skill_name": SKILL_NAME,
        "trigger": clean_fields["trigger"],
        "intended_action": clean_fields["intended_action"],
        "actual_action": clean_fields["actual_action"],
        "failure_point": clean_fields["failure_point"],
        "false_assumption": clean_fields["false_assumption"],
        "user_correction": clean_fields["user_correction"],
        "next_time_rule": clean_fields["next_time_rule"],
        "severity": args.severity,
        "redaction_applied": bool(redaction_types),
        "redaction_types": sorted(redaction_types),
    }
    log_path = output_root / "exception-log.jsonl"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    proposal_path = proposal_dir / f"{run_id}.md"
    proposal_path.write_text(
        "\n".join(
            (
                "# Patch Proposal",
                "",
                "## Сводка Сбоя",
                "",
                f"- Симптом: {clean_fields['failure_point']}",
                f"- Ложная предпосылка: {clean_fields['false_assumption']}",
                f"- Следующее правило: {clean_fields['next_time_rule']}",
                "",
                "## known-exceptions.yaml",
                "",
                f"- `symptom`: {clean_fields['failure_point']}",
                f"- `root_cause`: {clean_fields['false_assumption']}",
                f"- `do_next_time`: {clean_fields['next_time_rule']}",
                f"- `source_example`: sanitized run `{run_id}`",
                "",
                "## references/domain-playbook.md",
                "",
                clean_fields["playbook_rule"],
                "",
                "## Regression Test",
                "",
                clean_fields["regression_test"],
                "",
                "## Gate",
                "",
                "- Получить human approval на постоянное изменение.",
                "- Применить patch только к source repo, не к установленному cache.",
                "- Запустить `python3 -m pytest`.",
                "- Сделать commit с объяснением, какое исключение стало правилом.",
                "",
            )
        ),
        encoding="utf-8",
    )

    print(f"Санированная карточка добавлена: {log_path}")
    print(f"Patch proposal подготовлен: {proposal_path}")
    print("Исходный skill не изменён; для постоянного patch требуется одобрение.")


if __name__ == "__main__":
    main()
